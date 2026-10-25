# E-Bill Downloader - Licensing & Update Server

Serverless microservice deployed to Vercel for serial key activation, device hardware binding, and update distribution.

## Multi-Tenancy Architecture
This service is designed to run in your existing Supabase project alongside `BillScrapper` at zero additional cost ($0 forever). It uses table prefixing:
- `ebill_licenses`
- `ebill_license_devices`
- `ebill_app_updates`

## Vercel Deployment

1. **Deploy to Vercel:**
   Connect your GitHub repository to Vercel or run `vercel` inside `license_server/`.

2. **Configure Environment Variables in Vercel:**
   - `SUPABASE_URL`: (from your existing Supabase project)
   - `SUPABASE_SERVICE_ROLE_KEY`: (from your existing Supabase project)
   - `ADMIN_SECRET`: Strong secret key (e.g. `EBillDownloader_Secret_Key_2026`)
   - `GITHUB_REPO`: `your-username/EBillDownloader`
   - `GITHUB_TOKEN`: GitHub Personal Access Token (fine-grained, read-only on Releases)
   - `TABLE_LICENSES`: `ebill_licenses`
   - `TABLE_DEVICES`: `ebill_license_devices`
   - `TABLE_UPDATES`: `ebill_app_updates`
   - `KEY_PREFIX`: `EB`

3. **Run Database Migration in Supabase SQL Editor:**
   Execute `schema.sql` inside your Supabase project's SQL Editor.
