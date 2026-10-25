/**
 * E-Bill Downloader Licensing & Device-Limiting Server
 * Node.js / Express API backed by Supabase PostgreSQL
 */

require('dotenv').config();
const crypto = require('crypto');
const express = require('express');
const cors = require('cors');
const { createClient } = require('@supabase/supabase-js');

const app = express();
const PORT = process.env.PORT || 3000;

// Enable CORS and JSON parsing
app.use(cors());
app.use(express.json());

// Initialize Supabase Client
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const ADMIN_SECRET = process.env.ADMIN_SECRET;

// Table configurations (Multi-tenancy support)
const TABLE_LICENSES = process.env.TABLE_LICENSES || 'ebill_licenses';
const TABLE_DEVICES = process.env.TABLE_DEVICES || 'ebill_license_devices';
const TABLE_UPDATES = process.env.TABLE_UPDATES || 'ebill_app_updates';
const KEY_PREFIX = process.env.KEY_PREFIX || 'EB';

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
  console.error('ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment variables.');
  process.exit(1);
}

// Service role key allows bypassing RLS safely from the secure backend
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false }
});

// Plan mapping configurations
const PLAN_CONFIG = {
  '1_month': { duration_days: 30, max_devices: 1, label: '1 Month' },
  '3_months': { duration_days: 90, max_devices: 2, label: '3 Months' },
  '6_months': { duration_days: 180, max_devices: 2, label: '6 Months' },
  '1_year': { duration_days: 365, max_devices: 2, label: '1 Year' }
};

/**
 * Generate a random unique Serial Key in format: EB-XXXX-XXXX-XXXX
 * Uses unambiguous uppercase alphanumeric characters (excluding 0, O, 1, I)
 */
function generateSerialKey() {
  const CHARSET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
  const getChunk = (len = 4) => {
    const bytes = crypto.randomBytes(len);
    let str = '';
    for (let i = 0; i < len; i++) {
      str += CHARSET[bytes[i] % CHARSET.length];
    }
    return str;
  };
  return `${KEY_PREFIX}-${getChunk(4)}-${getChunk(4)}-${getChunk(4)}`;
}

// ====================================================================
// HEALTH CHECKS
// ====================================================================
app.get(['/', '/health'], (req, res) => {
  res.json({
    status: 'ok',
    app: 'E-Bill Downloader License Server',
    timestamp: new Date().toISOString()
  });
});

// ====================================================================
// CORE ACTIVATION / VERIFICATION LOGIC
// ====================================================================
async function handleLicenseVerification(req, res, { isExplicitActivation = false } = {}) {
  try {
    const { serial_key, device_id, os_info, candidate_ids } = req.body || {};

    if (!serial_key || typeof serial_key !== 'string') {
      return res.status(400).json({
        valid: false,
        status: 'bad_request',
        message: 'Serial key is required.'
      });
    }

    if (!device_id || typeof device_id !== 'string') {
      return res.status(400).json({
        valid: false,
        status: 'bad_request',
        message: 'Hardware device_id is required.'
      });
    }

    const cleanKey = serial_key.trim().toUpperCase();
    const cleanDeviceId = device_id.trim();
    const cleanOsInfo = (os_info && typeof os_info === 'string') ? os_info.trim() : 'Unknown OS';

    const candidateIds = Array.isArray(candidate_ids) && candidate_ids.length > 0
      ? candidate_ids.map(id => String(id).trim()).filter(Boolean)
      : [cleanDeviceId];

    // 1. Fetch license details from database
    const { data: license, error: licError } = await supabase
      .from(TABLE_LICENSES)
      .select('*')
      .eq('serial_key', cleanKey)
      .maybeSingle();

    if (licError) {
      console.error('[DB ERROR] Fetching license failed:', licError);
      return res.status(500).json({
        valid: false,
        status: 'server_error',
        message: 'Database query failed.'
      });
    }

    if (!license) {
      return res.status(404).json({
        valid: false,
        status: 'invalid',
        message: 'Invalid serial key. Please verify your purchase.'
      });
    }

    // 2. Check revocation
    if (license.is_revoked) {
      return res.status(403).json({
        valid: false,
        status: 'revoked',
        message: 'This serial key has been revoked by administration.'
      });
    }

    const now = new Date();

    // 3. First time activation: initialize activation and expiration dates
    if (!license.activated_at) {
      const durationDays = license.duration_days || 30;
      const expiresAt = new Date(now.getTime() + durationDays * 24 * 60 * 60 * 1000);

      const { data: updatedLic, error: updateError } = await supabase
        .from(TABLE_LICENSES)
        .update({
          activated_at: now.toISOString(),
          expires_at: expiresAt.toISOString()
        })
        .eq('id', license.id)
        .select()
        .single();

      if (updateError) {
        console.error('[DB ERROR] Activating license failed:', updateError);
        return res.status(500).json({
          valid: false,
          status: 'server_error',
          message: 'Failed to record activation timestamp.'
        });
      }

      license.activated_at = updatedLic.activated_at;
      license.expires_at = updatedLic.expires_at;
    }

    // 4. Check expiration date
    const expirationDate = new Date(license.expires_at);
    if (now > expirationDate) {
      return res.status(403).json({
        valid: false,
        status: 'expired',
        expires_at: license.expires_at,
        plan_type: license.plan_type,
        message: `Your subscription expired on ${expirationDate.toLocaleDateString()}. Please renew your key.`
      });
    }

    // 5. Query active registered devices for this license
    const { data: devices, error: devError } = await supabase
      .from(TABLE_DEVICES)
      .select('*')
      .eq('license_id', license.id);

    if (devError) {
      console.error('[DB ERROR] Querying devices failed:', devError);
      return res.status(500).json({
        valid: false,
        status: 'server_error',
        message: 'Failed to query device registrations.'
      });
    }

    const existingDeviceList = devices || [];
    const matchedDevice = existingDeviceList.find(d => candidateIds.includes(d.device_id));

    if (matchedDevice) {
      // Device recognized - update last_active timestamp and canonical device ID
      await supabase
        .from(TABLE_DEVICES)
        .update({
          device_id: cleanDeviceId,
          last_active: now.toISOString(),
          os_info: cleanOsInfo
        })
        .eq('id', matchedDevice.id);

      return res.json({
        valid: true,
        status: 'active',
        plan_type: license.plan_type,
        duration_days: license.duration_days,
        max_devices: license.max_devices,
        devices_count: existingDeviceList.length,
        activated_at: license.activated_at,
        expires_at: license.expires_at,
        message: 'Subscription is active and valid.'
      });
    }

    // 6. New device attempting to connect: check device limit
    if (existingDeviceList.length >= license.max_devices) {
      return res.status(403).json({
        valid: false,
        status: 'limit_reached',
        max_devices: license.max_devices,
        devices_count: existingDeviceList.length,
        message: `Device limit reached (${existingDeviceList.length}/${license.max_devices}). Contact support to transfer license.`
      });
    }

    // 7. Register new device
    const { error: insertDevError } = await supabase
      .from(TABLE_DEVICES)
      .insert({
        license_id: license.id,
        device_id: cleanDeviceId,
        os_info: cleanOsInfo,
        first_seen: now.toISOString(),
        last_active: now.toISOString()
      });

    if (insertDevError) {
      console.error('[DB ERROR] Registering new device failed:', insertDevError);
      return res.status(500).json({
        valid: false,
        status: 'server_error',
        message: 'Failed to bind device to license.'
      });
    }

    return res.json({
      valid: true,
      status: 'activated',
      plan_type: license.plan_type,
      duration_days: license.duration_days,
      max_devices: license.max_devices,
      devices_count: existingDeviceList.length + 1,
      activated_at: license.activated_at,
      expires_at: license.expires_at,
      message: 'License activated successfully on this device!'
    });

  } catch (err) {
    console.error('[EXCEPTION] handleLicenseVerification error:', err);
    return res.status(500).json({
      valid: false,
      status: 'internal_error',
      message: 'Unexpected server error occurred.'
    });
  }
}

app.post('/api/activate', (req, res) => handleLicenseVerification(req, res, { isExplicitActivation: true }));
app.post('/api/verify', (req, res) => handleLicenseVerification(req, res, { isExplicitActivation: false }));

// ====================================================================
// ADMIN KEY GENERATION (Protected by ADMIN_SECRET)
// ====================================================================
app.post('/api/admin/generate', async (req, res) => {
  try {
    const adminSecret = req.headers['x-admin-secret'];
    if (!ADMIN_SECRET || adminSecret !== ADMIN_SECRET) {
      return res.status(401).json({ error: 'Unauthorized: Invalid admin secret' });
    }

    const { plan_type, count = 1 } = req.body || {};

    if (!plan_type || !PLAN_CONFIG[plan_type]) {
      return res.status(400).json({
        error: `Invalid plan_type. Choose one of: ${Object.keys(PLAN_CONFIG).join(', ')}`
      });
    }

    const plan = PLAN_CONFIG[plan_type];
    const generatedKeys = [];

    for (let i = 0; i < Math.min(Number(count) || 1, 50); i++) {
      const serialKey = generateSerialKey();
      const { data, error } = await supabase
        .from(TABLE_LICENSES)
        .insert({
          serial_key: serialKey,
          plan_type: plan_type,
          duration_days: plan.duration_days,
          max_devices: plan.max_devices
        })
        .select()
        .single();

      if (error) {
        console.error('[DB ERROR] Key insertion failed:', error);
        return res.status(500).json({ error: 'Failed to insert serial key into database.' });
      }

      generatedKeys.push(data.serial_key);
    }

    return res.json({
      success: true,
      count: generatedKeys.length,
      keys: generatedKeys,
      plan_type: plan_type,
      duration_days: plan.duration_days,
      max_devices: plan.max_devices
    });

  } catch (err) {
    console.error('[ADMIN GENERATE ERROR]', err);
    return res.status(500).json({ error: 'Internal server error' });
  }
});

// ====================================================================
// AUTO-UPDATER API
// ====================================================================
const GITHUB_REPO = process.env.GITHUB_REPO || 'naqasht128/EBillDownloader';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';

function cleanReleaseNotes(raw) {
  if (!raw || typeof raw !== 'string') return '';
  const lines = raw.replace(/\r\n/g, '\n').split('\n');
  const cleaned = [];

  for (let line of lines) {
    let trimmed = line.trim();
    if (!trimmed) continue;

    // Skip automated GitHub comparison footer lines (e.g. **Full Changelog**: ...)
    if (/full changelog/i.test(trimmed)) continue;

    // Strip GitHub repository links, comparison URLs, and PR references
    if (/github\.com/i.test(trimmed)) {
      trimmed = trimmed
        .replace(/\s*in\s+https?:\/\/github\.com\S+/gi, '')
        .replace(/\[([^\]]+)\]\(https?:\/\/github\.com[^\)]*\)/gi, '$1')
        .replace(/https?:\/\/github\.com\S*/gi, '')
        .replace(/\s*by\s+@[\w-]+/gi, '')
        .trim();
    }

    // Strip any remaining raw URLs
    trimmed = trimmed.replace(/https?:\/\/\S+/gi, '').trim();

    // Clean markdown headings
    if (trimmed.startsWith('#')) {
      const headerText = trimmed.replace(/^#+\s*/, '').trim();
      if (/^(what's changed|whats changed|changelog|release notes|updates)$/i.test(headerText)) {
        continue;
      }
      trimmed = headerText;
    }

    if (!trimmed || /^[\*\-•:\s]+$/.test(trimmed)) continue;

    cleaned.push(trimmed);
  }

  return cleaned.join('\n').trim();
}

app.get('/api/updates/latest', async (req, res) => {
  try {
    try {
      const ghHeaders = {
        'User-Agent': 'EBillDownloader-LicenseServer',
        'Accept': 'application/vnd.github.v3+json'
      };
      if (GITHUB_TOKEN) {
        ghHeaders['Authorization'] = `Bearer ${GITHUB_TOKEN}`;
      }

      const ghUrl = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;
      const ghRes = await fetch(ghUrl, { headers: ghHeaders });

      if (ghRes.ok) {
        const data = await ghRes.json();
        const tag = (data.tag_name || '').replace(/^v/, '');
        const assets = data.assets || [];

        const isWin7 = (req.query.os || '').toLowerCase() === 'win7' || (req.headers['user-agent'] || '').toLowerCase().includes('windows nt 6.1');

        let setupAsset;
        if (isWin7) {
          setupAsset = assets.find(a => a.name.toLowerCase().includes('win7') && a.name.toLowerCase().includes('setup') && a.name.toLowerCase().endsWith('.exe'))
            || assets.find(a => a.name.toLowerCase().includes('win7') && a.name.toLowerCase().endsWith('.exe'));
        } else {
          setupAsset = assets.find(a => !a.name.toLowerCase().includes('win7') && a.name.toLowerCase().includes('setup') && a.name.toLowerCase().endsWith('.exe'))
            || assets.find(a => !a.name.toLowerCase().includes('win7') && a.name.toLowerCase().endsWith('.exe'));
        }

        if (!setupAsset) {
          setupAsset = assets.find(a => a.name.toLowerCase().includes('setup') && a.name.toLowerCase().endsWith('.exe'))
            || assets.find(a => a.name.toLowerCase().endsWith('.exe'));
        }

        if (setupAsset) {
          const host = req.get('host');
          const proto = req.headers['x-forwarded-proto'] || 'https';
          const dlUrl = setupAsset.browser_download_url || `${proto}://${host}/api/updates/download?asset_id=${setupAsset.id}`;
          return res.json({
            version: tag,
            file_name: setupAsset.name,
            file_size: setupAsset.size || 0,
            download_url: dlUrl,
            release_notes: cleanReleaseNotes(data.body)
          });
        }
      }
    } catch (ghErr) {
      console.warn('[GH FETCH WARN] Failed to fetch from GitHub API:', ghErr.message);
    }

    // Fallback: Check Supabase table
    try {
      const { data: updateRecord } = await supabase
        .from(TABLE_UPDATES)
        .select('*')
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();

      if (updateRecord && updateRecord.version) {
        return res.json({
          version: updateRecord.version.replace(/^v/, ''),
          file_name: updateRecord.file_name || 'EBillDownloader-Setup.exe',
          file_size: updateRecord.file_size || 0,
          download_url: updateRecord.download_url,
          release_notes: cleanReleaseNotes(updateRecord.release_notes)
        });
      }
    } catch (dbErr) {
      // Table check fallback
    }

    const fallbackVersion = (process.env.LATEST_VERSION || '1.0.0').replace(/^v/, '');
    const fallbackUrl = process.env.LATEST_DOWNLOAD_URL || '';
    return res.json({
      version: fallbackVersion,
      file_name: 'EBillDownloader-Setup.exe',
      download_url: fallbackUrl,
      release_notes: cleanReleaseNotes(process.env.LATEST_RELEASE_NOTES || '')
    });

  } catch (err) {
    console.error('[UPDATES ERROR]', err);
    return res.status(500).json({ error: 'Failed to check for updates' });
  }
});

app.get('/api/updates/download', async (req, res) => {
  try {
    const { asset_id } = req.query;

    if (asset_id && GITHUB_TOKEN) {
      const assetUrl = `https://api.github.com/repos/${GITHUB_REPO}/releases/assets/${asset_id}`;
      const ghRes = await fetch(assetUrl, {
        headers: {
          'User-Agent': 'EBillDownloader-LicenseServer',
          'Authorization': `Bearer ${GITHUB_TOKEN}`,
          'Accept': 'application/octet-stream'
        },
        redirect: 'follow'
      });

      if (!ghRes.ok) {
        return res.status(ghRes.status).send('Failed to fetch update asset from storage.');
      }

      const contentType = ghRes.headers.get('content-type') || 'application/octet-stream';
      const arrayBuffer = await ghRes.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);

      res.setHeader('Content-Type', contentType);
      res.setHeader('Content-Length', buffer.length);
      res.setHeader('Cache-Control', 'no-transform, public, max-age=300');
      res.setHeader('Accept-Ranges', 'bytes');
      res.setHeader('Content-Disposition', 'attachment; filename="EBillDownloader-Setup.exe"');

      return res.send(buffer);
    }

    const directUrl = process.env.LATEST_DOWNLOAD_URL;
    if (directUrl) {
      return res.redirect(directUrl);
    }

    return res.status(404).send('Download file not found.');
  } catch (err) {
    console.error('[DOWNLOAD PROXY ERROR]', err);
    return res.status(500).send('Error downloading update file.');
  }
});

app.post('/api/admin/set-update', async (req, res) => {
  try {
    const adminSecret = req.headers['x-admin-secret'];
    if (!ADMIN_SECRET || adminSecret !== ADMIN_SECRET) {
      return res.status(401).json({ error: 'Unauthorized: Invalid admin secret' });
    }

    const { version, download_url, file_name, release_notes } = req.body || {};
    if (!version) {
      return res.status(400).json({ error: 'Version is required.' });
    }

    const cleanVer = String(version).trim().replace(/^v/, '');

    const { error } = await supabase
      .from(TABLE_UPDATES)
      .upsert({
        version: cleanVer,
        download_url: download_url || '',
        file_name: file_name || 'EBillDownloader-Setup.exe',
        release_notes: release_notes || `Release v${cleanVer}`,
        updated_at: new Date().toISOString()
      }, { onConflict: 'version' });

    if (error) {
      console.error('[DB ERROR] set-update failed:', error);
      return res.status(500).json({ error: error.message });
    }

    return res.json({ success: true, message: `Update v${cleanVer} registered successfully!` });
  } catch (err) {
    console.error('[ADMIN SET UPDATE ERROR]', err);
    return res.status(500).json({ error: 'Internal server error' });
  }
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`====================================================`);
    console.log(`🚀 E-Bill Downloader License Server running on port ${PORT}`);
    console.log(`   Health check: http://localhost:${PORT}/health`);
    console.log(`====================================================`);
  });
}

module.exports = app;
