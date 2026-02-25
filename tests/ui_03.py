import random
import string
import re
import os
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

def random_suffix(length=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def login(page: Page):
    page.goto("http://localhost:8000/control/login")
    page.wait_for_timeout(2000)
    email_input = page.locator('//*[@id="id_email"]')
    email_input.fill(os.getenv("TEST_EMAIL"))
    page.wait_for_timeout(1000)
    password_input = page.locator('//*[@id="id_password"]')
    password_input.fill(os.getenv("TEST_PASSWORD"))
    page.wait_for_timeout(1000)
    page.locator('button[type="submit"]').click()
    page.wait_for_timeout(2000)
    
    page.locator('//*[@id="button-sudo"]').click()
    page.wait_for_timeout(1000)
    
    page.goto("http://localhost:8000/control/events/")
    page.wait_for_timeout(1000)

def test_create_event(page: Page):
    login(page)
    suffix = random_suffix()
    page.wait_for_timeout(2000)
    page.locator('//*[@id="page-wrapper"]/div/p[2]/a').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="page-wrapper"]/div/form/div[1]/div/span/span[1]/span').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="select2-id_foundation-organizer-results"]/li[1]/span/span').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="id_foundation-locales_0_0"]').check()
    page.locator('//*[@id="id_foundation-locales_1_27"]').check()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="page-wrapper"]/div/form/div/button[1]').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="id_basics-name_0"]').fill(f"Drake {suffix}")
    page.locator('//*[@id="id_basics-date_from_0"]').fill("2026-02-02")
    page.locator('//*[@id="id_basics-date_from_1"]').fill("00:15:00")
    page.locator('//*[@id="id_basics-location_0"]').fill("Istanbul, Turkey")
    page.locator('//*[@id="id_basics-slug"]').fill(f"drake-{suffix}")
    page.locator('//*[@id="id_basics-tax_rate"]').fill("10")
    page.wait_for_timeout(1000)
    page.locator('//*[@id="page-wrapper"]/div/form/div/button[1]').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="select2-id_copy-copy_from_event-container"]').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="select2-id_copy-copy_from_event-results"]/li[1]/span/span[1]').click()
    page.wait_for_timeout(1000)
    page.locator('//*[@id="page-wrapper"]/div/form/div[3]/button[1]').click()
    page.wait_for_timeout(2000)
