-- ====================================================================
-- E-Bill Downloader - Supabase PostgreSQL Database Schema
-- Run this script in the Supabase SQL Editor: Dashboard -> SQL Editor
-- This supports Multi-Tenant deployment alongside BillScrapper!
-- ====================================================================

-- 1. Ensure required extensions are available
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ====================================================================
-- 2. Table: ebill_licenses
-- Stores issued serial keys, subscription plans, and validity
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.ebill_licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_key TEXT UNIQUE NOT NULL,
    plan_type TEXT NOT NULL CHECK (plan_type IN ('1_month', '3_months', '6_months', '1_year')),
    duration_days INTEGER NOT NULL CHECK (duration_days IN (30, 90, 180, 365)),
    max_devices INTEGER NOT NULL CHECK (max_devices IN (1, 2)),
    activated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ====================================================================
-- 3. Table: ebill_license_devices
-- Tracks hardware devices activated under each serial key
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.ebill_license_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_id UUID NOT NULL REFERENCES public.ebill_licenses(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    os_info TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ebill_license_device UNIQUE (license_id, device_id)
);

-- ====================================================================
-- 4. Table: ebill_app_updates
-- Tracks desktop application update versions and download artifacts
-- ====================================================================
CREATE TABLE IF NOT EXISTS public.ebill_app_updates (
    version VARCHAR(32) PRIMARY KEY,
    download_url TEXT NOT NULL,
    file_name VARCHAR(128) DEFAULT 'EBillDownloader-Setup.exe',
    file_size BIGINT DEFAULT 0,
    release_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ====================================================================
-- 5. Performance Indexes
-- ====================================================================
CREATE INDEX IF NOT EXISTS idx_ebill_licenses_serial_key ON public.ebill_licenses (serial_key);
CREATE INDEX IF NOT EXISTS idx_ebill_licenses_expires_at ON public.ebill_licenses (expires_at);
CREATE INDEX IF NOT EXISTS idx_ebill_license_devices_license_id ON public.ebill_license_devices (license_id);
CREATE INDEX IF NOT EXISTS idx_ebill_license_devices_device_id ON public.ebill_license_devices (device_id);

-- ====================================================================
-- 6. Row Level Security (RLS) Configuration
-- Secure tables so only backend service role key can modify data.
-- ====================================================================
ALTER TABLE public.ebill_licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ebill_license_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ebill_app_updates ENABLE ROW LEVEL SECURITY;

-- Deny anon/public direct access to licenses
DROP POLICY IF EXISTS "Deny anon access on ebill_licenses" ON public.ebill_licenses;
CREATE POLICY "Deny anon access on ebill_licenses" ON public.ebill_licenses
    FOR ALL TO anon USING (false);

-- Deny anon/public direct access to devices
DROP POLICY IF EXISTS "Deny anon access on ebill_license_devices" ON public.ebill_license_devices;
CREATE POLICY "Deny anon access on ebill_license_devices" ON public.ebill_license_devices
    FOR ALL TO anon USING (false);

-- Allow public read on updates
DROP POLICY IF EXISTS "Allow anon read on ebill_app_updates" ON public.ebill_app_updates;
CREATE POLICY "Allow anon read on ebill_app_updates" ON public.ebill_app_updates
    FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS "Deny anon modify on ebill_app_updates" ON public.ebill_app_updates;
CREATE POLICY "Deny anon modify on ebill_app_updates" ON public.ebill_app_updates
    FOR INSERT TO anon WITH CHECK (false);

-- Comments for documentation
COMMENT ON TABLE public.ebill_licenses IS 'Serial keys, plans, and activation lifecycles for E-Bill Downloader.';
COMMENT ON TABLE public.ebill_license_devices IS 'Hardware devices bound to active licenses with device limits.';
COMMENT ON TABLE public.ebill_app_updates IS 'Release versions and download metadata for E-Bill Downloader desktop client.';
