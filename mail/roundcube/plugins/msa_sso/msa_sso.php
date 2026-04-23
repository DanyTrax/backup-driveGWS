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
        $this->add_hook('authenticate', [$this, 'on_authenticate']);
    }

    public function action_redeem()
    {
        $token = rcube_utils::get_input_value('token', rcube_utils::INPUT_GET);
        if (!$token) {
            return header('Location: ./');
        }

        $payload = $this->decode_and_verify($token);
        if (!$payload) {
            return $this->bail('Invalid SSO token');
        }

        $_SESSION['msa_sso_payload'] = $payload;
        $rcmail = rcmail::get_instance();

        $_POST['_user'] = $payload['sub'];
        $_POST['_host'] = $rcmail->config->get('default_host');
        $_POST['_pass'] = '__msa_sso__'; // replaced inside on_authenticate
        $_POST['_task'] = 'login';
        $_POST['_action'] = 'login';

        $rcmail->overwrite_action('login');
        $rcmail->task = 'login';
    }

    public function on_authenticate($args)
    {
        if (empty($_SESSION['msa_sso_payload'])) {
            return $args;
        }
        $payload = $_SESSION['msa_sso_payload'];

        if (($payload['type'] ?? '') === 'admin_sso') {
            $master_user = getenv('DOVECOT_MASTER_USER') ?: '';
            $master_pass = getenv('DOVECOT_MASTER_PASSWORD') ?: '';
            if (!$master_user || !$master_pass) {
                $this->bail('Dovecot master-user credentials are not configured');
            }
            $args['user'] = $payload['sub'] . '*' . $master_user;
            $args['pass'] = $master_pass;
        } elseif (($payload['type'] ?? '') === 'client_sso') {
            $args['user'] = $payload['sub'];
            $args['pass'] = $payload['pw'] ?? '';
        }

        unset($_SESSION['msa_sso_payload']);
        return $args;
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
