import re
import os
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

load_dotenv() 

def test_login(page: Page):
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

    expect(page).to_have_url("http://localhost:8000/control/")
