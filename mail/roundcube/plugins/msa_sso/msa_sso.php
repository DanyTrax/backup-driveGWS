<?php
/**
 * MSA SSO plugin for Roundcube.
 *
 * Accepts a short-lived single-use JWT issued by the MSA Backup Commander
 * backend via the URL:
 *
 *      https://webmail.example.com/?_task=login&_action=plugin.msa_sso&rid=<id>
 *   (o el legacy largo) …&token=<jwt>
 *
 * The token is signed with the platform SECRET_KEY (HS256) and encodes:
 *   - sub:  user@domain.com
 *   - type: "admin_sso" | "client_sso"
 *   - jti:  single-use id (tracked in Redis)
 *   - iat / exp
 *   - iss:  "msa-backup-commander"
 *
 * admin_sso  -> uses Dovecot master-user authentication.
 * client_sso -> the platform has already set the user's IMAP password, so the
 *               plugin generates a random one-time-use password via the REST
 *               helper and logs in with it. The platform also exposes a
 *               dedicated endpoint to re-hash the password after use.
 *
 * Requires firebase/php-jwt (shipped as vendor bundle) and a Redis extension
 * or phpredis available in the PHP container.
 */

require_once __DIR__ . '/vendor/autoload.php';

use Firebase\JWT\JWT;
use Firebase\JWT\Key;

class msa_sso extends rcube_plugin
{
    public $task = 'login|mail|settings';

    /** Evita doble ejecución si startup y register_action se disparan en el mismo request. */
    private static $redeem_ran = false;

    public function init()
    {
        // En algunas instalaciones 1.6.x el login se pinta antes de enrutar `plugin.msa_sso`.
        $this->add_hook('startup', [$this, 'hook_startup_redeem']);
        $this->register_action('plugin.msa_sso', [$this, 'action_redeem']);
    }

    public function hook_startup_redeem(): void
    {
        if (self::$redeem_ran) {
            return;
        }
        $act = (string) ($_GET['_action'] ?? $_POST['_action'] ?? '');
        if ($act !== 'plugin.msa_sso') {
            return;
        }
        $task = (string) ($_GET['_task'] ?? $_POST['_task'] ?? 'login');
        if ($task !== 'login') {
            return;
        }
        $rc = rcmail::get_instance();
        if ($rc->get_user_id()) {
            return;
        }
        $this->action_redeem();
    }

    /**
     * Valida el JWT, marca JTI en Redis y llama a rcmail::login() explícitamente.
     * Rellenar solo $_POST no dispara el login en Roundcube 1.6: la pantalla
     * quedaba en el formulario aunque la URL llevara el token.
     */
    public function action_redeem()
    {
        if (self::$redeem_ran) {
            return;
        }
        self::$redeem_ran = true;
        $token = $this->resolve_token_from_request();
        if (!$token) {
            if (getenv('MSA_SSO_DEBUG') === '1') {
                $ridq = (string) ($_GET['rid'] ?? '');
                error_log(
                    'msa_sso: no JWT (rid missing in Redis, wrong secret, or rid stripped by filters). ' .
                    'rid_present=' . ($ridq !== '' ? 'yes len=' . strlen($ridq) : 'no') .
                    ' redis_host=' . (getenv('REDIS_HOST') ?: 'default')
                );
            }
            header('Location: ./index.php?_task=login');
            exit;
        }

        $payload = $this->decode_and_verify($token);
        if (!$payload) {
            $this->bail('Invalid SSO token');
        }

        $rcmail = rcmail::get_instance();
        $host = $rcmail->config->get('default_host');
        $type = $payload['type'] ?? '';

        if ($type === 'admin_sso') {
            $master_user = getenv('DOVECOT_MASTER_USER') ?: '';
            $master_pass = getenv('DOVECOT_MASTER_PASSWORD') ?: '';
            if (!$master_user || !$master_pass) {
                $this->bail('Dovecot master-user credentials are not configured');
            }
            $user = $payload['sub'] . '*' . $master_user;
            $pass = $master_pass;
        } elseif ($type === 'client_sso') {
            $user = $payload['sub'];
            $pass = $payload['pw'] ?? '';
            if ($pass === '') {
                $this->bail('Client SSO token missing password claim');
            }
        } else {
            $this->bail('Invalid SSO type');
        }

        if (!$rcmail->login($user, $pass, $host, true)) {
            $code = $rcmail->login_error();
            $stor = $rcmail->get_storage();
            $detail = $stor ? $stor->get_error() : '';
            $this->bail('IMAP login failed after SSO (code: ' . ($code ?? 'n/a') . ') ' . $detail);
        }

        header('Location: ./?_task=mail');
        exit;
    }

    /**
     * Prioridad: `rid` (JWT guardado en Redis, URL corta) → `token` en query/post (legacy).
     */
    private function resolve_token_from_request(): string
    {
        // Leer `rid` en crudo: rcube_utils a veces filtra caracteres o falla con query raras en proxies.
        $rid = (string) ($_GET['rid'] ?? $_POST['rid'] ?? '');
        if ($rid === '') {
            $rid = (string) (rcube_utils::get_input_value('rid', rcube_utils::INPUT_GET) ?? '');
        }
        if ($rid === '') {
            $rid = (string) (rcube_utils::get_input_value('rid', rcube_utils::INPUT_POST) ?? '');
        }
        if ($rid !== '') {
            $t = $this->fetch_jwt_by_rid($rid);
            if ($t !== null && $t !== '') {
                return $t;
            }
        }
        $token = rcube_utils::get_input_value('token', rcube_utils::INPUT_GET);
        if (!$token) {
            $token = rcube_utils::get_input_value('token', rcube_utils::INPUT_POST);
        }
        if (!$token && !empty($_GET['token'])) {
            $token = (string) $_GET['token'];
        }
        return $token ? (string) $token : '';
    }

    /**
     * Saca el JWT almacenado con `issue_sso_jwt` bajo sso:rid:* y lo consume.
     */
    private function fetch_jwt_by_rid(string $rid): ?string
    {
        if (strlen($rid) > 256) {
            return null;
        }
        $host = getenv('REDIS_HOST') ?: 'redis';
        $port = (int) (getenv('REDIS_PORT') ?: 6379);
        $pwd  = getenv('REDIS_PASSWORD') ?: null;

        $redis = new \Redis();
        try {
            if (!$redis->connect($host, $port, 2.0)) {
                if (getenv('MSA_SSO_DEBUG') === '1') {
                    error_log("msa_sso: redis connect failed host={$host} port={$port}");
                }
                return null;
            }
            if ($pwd) {
                $redis->auth($pwd);
            }
            $key = 'sso:rid:' . $rid;
            $jwt = $redis->get($key);
            if ($jwt === false || $jwt === null || $jwt === '') {
                if (getenv('MSA_SSO_DEBUG') === '1') {
                    error_log("msa_sso: redis key missing or empty: {$key} (API and webmail must share the same Redis)");
                }
                return null;
            }
            $redis->del($key);
            return (string) $jwt;
        } catch (\Throwable $e) {
            if (getenv('MSA_SSO_DEBUG') === '1') {
                error_log('msa_sso: fetch_jwt_by_rid: ' . $e->getMessage());
            }
            return null;
        } finally {
            try { $redis->close(); } catch (\Throwable $e) {}
        }
    }

    private function decode_and_verify(string $token): ?array
    {
        $secret = getenv('MSA_SSO_SECRET') ?: getenv('SECRET_KEY');
        if (!$secret) {
            return null;
        }
        try {
            $decoded = (array) JWT::decode($token, new Key($secret, 'HS256'));
        } catch (\Throwable $e) {
            return null;
        }
        $jti = $decoded['jti'] ?? null;
        $type = $decoded['type'] ?? '';
        $iss = $decoded['iss'] ?? '';
        if ($iss !== 'msa-backup-commander') {
            return null;
        }
        if (!$jti || !in_array($type, ['admin_sso', 'client_sso'], true)) {
            return null;
        }
        if (!$this->claim_jti($jti)) {
            return null;
        }
        return $decoded;
    }

    /**
     * Atomically consume `sso:jti:<jti>` in Redis so every token is usable once.
     */
    private function claim_jti(string $jti): bool
    {
        $host = getenv('REDIS_HOST') ?: 'redis';
        $port = (int) (getenv('REDIS_PORT') ?: 6379);
        $pwd  = getenv('REDIS_PASSWORD') ?: null;

        $redis = new \Redis();
        try {
            if (!$redis->connect($host, $port, 2.0)) {
                return false;
            }
            if ($pwd) {
                $redis->auth($pwd);
            }
            $key = 'sso:jti:' . $jti;
            $current = $redis->get($key);
            if ($current !== 'pending') {
                return false;
            }
            $ok = $redis->set($key, 'used', ['XX', 'EX' => 300]);
            return $ok !== false;
        } catch (\Throwable $e) {
            return false;
        } finally {
            try { $redis->close(); } catch (\Throwable $e) {}
        }
    }

    private function bail(string $msg): void
    {
        http_response_code(401);
        header('Content-Type: text/plain; charset=utf-8');
        echo $msg;
        exit;
    }
}
