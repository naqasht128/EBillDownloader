# ⚡ E-Bill Downloader

> Production-grade desktop application to automate batch downloading, high-resolution A4 auto-formatting, serial number stamping, and PDF merging of utility electricity bills. Built on the **Replication Blueprint Architecture** with hardware-locked licensing, auto-updates, native C++ binary protection, and multi-OS CI/CD automation.

---

## 📑 Table of Contents
1. [Key Features](#-key-features)
2. [Architecture Overview](#-architecture-overview)
3. [Quick Start (Local Development)](#-quick-start-local-development)
4. [Multi-Tenancy Supabase Licensing Setup](#-multi-tenancy-supabase-licensing-setup)
5. [Admin Key Generator Tool](#-admin-key-generator-tool)
6. [Compilation & Packaging](#-compilation--packaging)
7. [Automated One-Command Releases](#-automated-one-command-releases)
8. [File Structure](#-file-structure)

---

## 🌟 Key Features

* **Batch Automation:** Reads Excel files (`.xlsx`) containing Account Numbers / Consumer IDs in Column A and optional Serial Numbers in Column B.
* **CDP High-Res Capture:** Uses Chrome DevTools Protocol (`Page.printToPDF`) for pixel-perfect vector printing.
* **Intelligent A4 Auto-Fitting:** Uses PyMuPDF (`fitz`) to crop whitespace/watermarks and center bills squarely onto standardized A4 sheets.
* **Serial Number Stamping:** Option to stamp `Sr. No. X` onto the top-right corner of each bill for administrative filing.
* **Merge or Separate:** Option to save separate individual PDFs or automatically merge all bills into a single sorted workbook PDF using `pypdf`.
* **State Machine:** Accurately detects loading delays, "Bill not Found", "Wrong AC No.", and dynamically retries without hanging.
* **VS Code Dark+ GUI:** Clean Tkinter desktop interface with real-time progress bars, stats counters, pause/resume controls, and live log stream.
* **Hardware-Locked Licensing:** Multi-stage failover HWID binding (Registry MachineGuid, PowerShell CIM UUID, WMIC, MAC Node) with offline grace period caching.
* **In-App Auto-Updater:** Automatically detects newer versions on startup, downloads the installer with progress display, and performs silent in-place upgrades.
* **Proprietary Code Protection:** Full Nuitka native C++ compilation (`.pyd`) prevents decompilation and reverse-engineering.

---

## 🏗 Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. DESKTOP CLIENT                               │
│  • Pure Python GUI (Tkinter VS Code Dark+ Theme)                       │
│  • Hardware Binding: BIOS UUID + MachineGuid + MAC Node                │
│  • In-App Auto-Updater (Detects Windows 7 vs Windows 10/11)            │
│  • Protected: Source code compiled to native C++ .pyd machine code     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS (Encrypted)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               2. CLOUD LICENSING & UPDATE SERVER (Vercel)              │
│  • Express.js Serverless Microservice                                  │
│  • Endpoints: /activate, /verify, /admin/generate, /updates/latest     │
│  • Securely proxies GitHub Releases without exposing GitHub tokens     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Service Role Key
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  3. DATABASE LAYER (Supabase Multi-Tenant)             │
│  • PostgreSQL with Row Level Security (RLS)                            │
│  • Co-exists in your existing Supabase project ($0 Free Tier forever)  │
│  • Tables: ebill_licenses, ebill_license_devices, ebill_app_updates    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (Local Development)

### 1. Requirements
* Python 3.10, 3.11, or 3.12 (64-bit)
* Google Chrome installed

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Application
```bash
python main.py
```

---

## 🛡 Multi-Tenancy Supabase Licensing Setup

Because Supabase allows 2 active free projects, **E-Bill Downloader** shares your existing Supabase project with `BillScrapper` at zero additional cost using table prefixing:

1. Open your Supabase project dashboard -> **SQL Editor**.
2. Run the SQL script located at [`license_server/schema.sql`](license_server/schema.sql). This creates:
   - `ebill_licenses`
   - `ebill_license_devices`
   - `ebill_app_updates`
3. Deploy [`license_server`](license_server/) to Vercel:
   ```bash
   cd license_server
   vercel
   ```
4. Set the following Environment Variables in Vercel:
   - `SUPABASE_URL`: *(Your existing Supabase URL)*
   - `SUPABASE_SERVICE_ROLE_KEY`: *(Your existing Supabase Service Role Key)*
   - `ADMIN_SECRET`: *(A secret key for generating serial keys, e.g. `EBSecretKey2026`)*
   - `GITHUB_REPO`: `your-username/EBillDownloader`
   - `GITHUB_TOKEN`: *(GitHub PAT with read access to Releases)*
   - `TABLE_LICENSES`: `ebill_licenses`
   - `TABLE_DEVICES`: `ebill_license_devices`
   - `TABLE_UPDATES`: `ebill_app_updates`
   - `KEY_PREFIX`: `EB`

---

## 🔑 Admin Key Generator Tool

The owner can generate new customer subscription keys (`EB-XXXX-XXXX-XXXX`) and auto-copy them to the clipboard using `generate_key.py`:

```bash
# Launch Dark-Themed GUI
python generate_key.py --gui

# Or Generate via CLI
python generate_key.py --plan 1_month
python generate_key.py --plan 3_months
python generate_key.py --plan 6_months
python generate_key.py --plan 1_year
```

---

## 📦 Compilation & Packaging

### 1. Compile Source Code to Native C++ Binary (.pyd)
```bash
pip install nuitka
python scripts/compile_nuitka.py
```
This compiles `main.py` into machine code (`main.*.pyd`) and deletes the plaintext `.py` file.

### 2. Package with PyInstaller
```bash
pip install pyinstaller
pyinstaller EBillDownloader.spec --clean
```

### 3. Build Windows Installer (Inno Setup)
```bash
iscc /DAppVersion=1.0.0 installer.iss
```
Generates `dist/EBillDownloader-Setup.exe`.

---

## 🚢 Automated One-Command Releases

Pushing updates and building multi-platform installers is automated:

```bash
python release.py 1.0.1 -m "Fixed PDF layout scaling and improved speed"
```

This single command:
1. Verifies Python syntax (`py_compile`).
2. Updates `APP_VERSION` across `main.py` and `installer.iss`.
3. Commits and pushes changes to `origin/main`.
4. Pushes tag `v1.0.1` to trigger GitHub Actions.
5. GitHub Actions builds Windows 10/11 x64, Windows 7 x86 (with bundled VC++ runtime), and Linux binaries.
6. Publishes GitHub Release and broadcasts update notifications to all active desktop app users!

---

## 📂 File Structure

```
EBillDownloader/
├── .github/
│   └── workflows/
│       └── build.yml               # Multi-OS CI/CD Pipeline
├── assets/
│   ├── app.ico                     # Multi-resolution icon
│   └── app.png                     # Window header icon
├── license_server/                 # Vercel Serverless Licensing API
│   ├── api/
│   │   └── index.js
│   ├── server.js                   # Express API (licensing, updates, admin)
│   ├── schema.sql                  # Supabase schema (ebill_* tables)
│   ├── package.json
│   └── vercel.json
├── scripts/
│   └── compile_nuitka.py           # Native C++ binary compilation
├── installer.iss                   # Inno Setup Windows installer script
├── EBillDownloader.spec            # PyInstaller specification
├── launcher.py                     # Entry point bootstrapping compiled .pyd
├── main.py                         # Desktop GUI & Downloader Engine
├── generate_key.py                 # Admin Serial Key Generator tool
├── generate_key.spec               # PyInstaller spec for Admin tool
├── release.py                      # One-command release & update broadcaster
├── requirements.txt                # Runtime Python dependencies
├── .gitignore
└── README.md
```
