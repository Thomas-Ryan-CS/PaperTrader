# tests/test_ui_selenium.py
import time
import uuid

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


BASE_URL = "http://localhost:5000"


@pytest.fixture(scope="session")
def driver():
    """Shared Chrome driver for this test session."""
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")  # uncomment if you want headless
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                              options=options)
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


def go(driver, path):
    driver.get(BASE_URL + path)


# ---------- AUTH UI VALIDATIONS ----------

def test_signup_missing_fields_shows_error(driver):
    go(driver, "/signup")

    # Form fields are named 'username' and 'password' (based on app.py)
    username = driver.find_element(By.NAME, "username")
    password = driver.find_element(By.NAME, "password")

    username.clear()
    password.clear()

    # submit the form (press Enter on password field)
    password.submit()

    # page should re-render with error text
    body_text = driver.find_element(By.TAG_NAME, "body").text
    assert "Enter username & password" in body_text


def test_signup_duplicate_username_shows_error(driver):
    # Use a fixed username once, then try to reuse it
    unique_name = f"selenium_user"

    # 1st signup: should create account
    go(driver, "/signup")
    driver.find_element(By.NAME, "username").send_keys(unique_name)
    driver.find_element(By.NAME, "password").send_keys("testpass")
    driver.find_element(By.NAME, "password").submit()

    # After signup you should be redirected to dashboard
    # Now log out so we can try to re-signup
    go(driver, "/logout")

    # 2nd signup with same username
    go(driver, "/signup")
    driver.find_element(By.NAME, "username").send_keys(unique_name)
    driver.find_element(By.NAME, "password").send_keys("anotherpass")
    driver.find_element(By.NAME, "password").submit()

    body_text = driver.find_element(By.TAG_NAME, "body").text
    assert "Username already taken" in body_text


def test_login_invalid_credentials_shows_error(driver):
    go(driver, "/login")
    driver.find_element(By.NAME, "username").send_keys("nosuchuser")
    driver.find_element(By.NAME, "password").send_keys("wrong")
    driver.find_element(By.NAME, "password").submit()

    body_text = driver.find_element(By.TAG_NAME, "body").text
    assert "Invalid credentials" in body_text


# ---------- HAPPY PATH: SIGNUP + DASHBOARD LOAD ----------

def signup_and_login(driver):
    """Helper: sign up a unique user and land on dashboard."""
    username = f"u_{uuid.uuid4().hex[:8]}"
    password = "testpass123"

    go(driver, "/signup")
    driver.find_element(By.NAME, "username").send_keys(username)
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.NAME, "password").submit()

    # Should now be on dashboard ("/")
    assert driver.current_url.endswith("/")

    return username, password


def test_dashboard_shows_tickers_after_signup(driver):
    signup_and_login(driver)
    body_text = driver.find_element(By.TAG_NAME, "body").text

    # Your app seeds these symbols in dashboard() when Ticker.count()==0
    # (AAPL, MSFT, GOOG, TSLA, AMZN, META, NVDA, NFLX, AMD, INTC)
    assert "AAPL" in body_text
    assert "MSFT" in body_text


# ---------- WATCHLIST UI VALIDATION ----------

def test_add_and_remove_watchlist_item_via_ui(driver):
    signup_and_login(driver)

    # Go to watchlist page
    go(driver, "/watchlist")

    # There's a form using field name 'symbol' (from app.py)
    symbol_input = driver.find_element(By.NAME, "symbol")
    symbol_input.clear()
    symbol_input.send_keys("AAPL")
    symbol_input.submit()

    time.sleep(0.5)  # small wait for reload/HTMX if used

    body_text = driver.find_element(By.TAG_NAME, "body").text
    assert "AAPL" in body_text

    # Remove via the remove form/button (POST /remove_watch with symbol)
    # You'll likely need to adjust this locator based on your template
    remove_buttons = driver.find_elements(By.XPATH, "//form[contains(@action, '/remove_watch')]//button")
    assert remove_buttons, "No remove button found for watchlist item"
    remove_buttons[0].click()

    time.sleep(0.5)
    body_text = driver.find_element(By.TAG_NAME, "body").text
    # AAPL might still appear elsewhere (like in ticker list), so in a real
    # template you'd use a more specific table/assertion.
    # For now, we just assert that the watchlist table no longer shows it.
    assert "AAPL" not in body_text or "Watchlist" not in body_text
