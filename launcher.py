#!/usr/bin/env python3
"""E-Bill Downloader - Application Launcher.
Bootstraps the application by delegating directly to the compiled native binary module (main.pyd).
"""

import sys

# Ensure PyInstaller's static scanner includes all dynamic runtime dependencies required by main.pyd
if False:
    import openpyxl
    import requests
    import fitz
    import pypdf
    import selenium
    import selenium.webdriver
    import selenium.webdriver.chrome
    import selenium.webdriver.chrome.options
    import selenium.webdriver.chrome.service
    import selenium.webdriver.chrome.webdriver
    import selenium.webdriver.common.by
    import selenium.webdriver.common.keys
    import selenium.webdriver.common.action_chains
    import selenium.webdriver.common.desired_capabilities
    import selenium.webdriver.common.print_page_options
    import selenium.webdriver.support.ui
    import selenium.webdriver.support.expected_conditions
    import selenium.common.exceptions
    import webdriver_manager
    import webdriver_manager.chrome
    import webdriver_manager.core
    import webdriver_manager.core.os_manager
    import webdriver_manager.core.download_manager
    import webdriver_manager.core.driver_cache_manager
    import webdriver_manager.core.logger

import main

if __name__ == "__main__":
    main.start_app()
