<?php
/**
 * MSA Backup Commander — Roundcube override config
 * Shipped into the container read-only; base image loads this after its defaults.
 */

// Force single IMAP backend (internal dovecot). Users cannot change.
$config['default_host']       = getenv('ROUNDCUBEMAIL_DEFAULT_HOST') ?: 'tls://dovecot';
$config['default_port']       = (int)(getenv('ROUNDCUBEMAIL_DEFAULT_PORT') ?: 143);
$config['imap_timeout']       = 60;
$config['imap_cache']         = 'db';
$config['messages_cache']     = 'db';
$config['session_lifetime']   = 60;          // minutes
$config['login_rate_limit']   = 5;
$config['force_https']        = false;       // NPM terminates TLS
$config['use_https']          = false;
$config['trusted_host_patterns'] = ['.*'];   // NPM hostname varies; adjust later in prod

// SMTP disabled: this is a backup viewer, not a mail client.
$config['smtp_server']        = '';
$config['smtp_log']           = false;

// Disable risky features for read-only backup browsing.
$config['disabled_actions']   = [];          // allow move/flag/delete for restore-to-original workflows

// Plugins
$config['plugins'] = array_unique(array_merge(
    (array)($config['plugins'] ?? []),
    ['archive', 'zipdownload', 'msa_sso']
));

// Look & feel
$config['skin']               = 'elastic';
$config['product_name']       = 'MSA Backup Webmail';
$config['support_url']        = '';
$config['language']           = 'es_ES';

// Log directory (inside container)
$config['log_driver']         = 'stdout';
$config['log_level']          = 1;
