<?php
/**
 * MSA SSO plugin for Roundcube.
 *
 * Accepts a short-lived single-use JWT issued by the MSA Backup Commander
 * backend via the URL:
 *
 *      https://webmail.example.com/?_action=plugin.msa_sso&token=<jwt>
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

    public function init()
    {
        $this->register_action('plugin.msa_sso', [$this, 'action_redeem']);
    }

    /**
     * Valida el JWT, marca JTI en Redis y llama a rcmail::login() explícitamente.
     * Rellenar solo $_POST no dispara el login en Roundcube 1.6: la pantalla
     * quedaba en el formulario aunque la URL llevara el token.
     */
    public function action_redeem()
    {
        $token = rcube_utils::get_input_value('token', rcube_utils::INPUT_GET);
        if (!$token) {
            $token = rcube_utils::get_input_value('token', rcube_utils::INPUT_POST);
        }
        if (!$token) {
            header('Location: ./');
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
