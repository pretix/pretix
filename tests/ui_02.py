import string
import random
import re
import os
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

load_dotenv()

def random_suffix(length=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def login(page: Page):
    page.goto(os.getenv("BASE_URL", "http://localhost:8000/control/login"))
    page.wait_for_timeout(2000)
    email_input = page.locator('//*[@id="id_email"]')
    email_input.fill(os.getenv("TEST_EMAIL"))
    page.wait_for_timeout(1000)
    password_input = page.locator('//*[@id="id_password"]')
    password_input.fill(os.getenv("TEST_PASSWORD"))
    page.wait_for_timeout(1000)
    page.locator('button[type="submit"]').click()
    page.wait_for_timeout(2000)

def test_create_organizer(page: Page):
    login(page)

    suffix = random_suffix()

    page.locator('//*[@id="button-sudo"]').click()
    page.wait_for_timeout(1000)

    page.locator('//*[@id="side-menu"]/li[3]/a').click()
    page.wait_for_timeout(1000)

    page.locator('//*[@id="page-wrapper"]/div/p[2]/a').click()
    page.wait_for_timeout(1000)

    page.locator('//*[@id="id_name"]').fill(f"Test Organizer {suffix}")
    page.locator('//*[@id="id_slug"]').fill(f"test-organizer-{suffix}")

    page.locator('//*[@id="page-wrapper"]/div/form/div/button').click()
    page.wait_for_timeout(1000)

    expect(page.locator('//*[@id="page-wrapper"]/div/div[1]')).to_be_visible()
