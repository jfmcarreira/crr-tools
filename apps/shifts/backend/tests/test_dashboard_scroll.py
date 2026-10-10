from datetime import date

import pytest


@pytest.mark.parametrize("explicit_month", [False, True])
def test_current_month_scrolls_to_today(client, explicit_month):
    today = date.today()
    url = f"/?year={today.year}&month={today.month}" if explicit_month else "/"

    response = client.get(url)

    assert response.status_code == 200
    assert 'class="day-card today"' in response.text
    assert "list.scrollTo({" in response.text
    assert "today.getBoundingClientRect().top - list.getBoundingClientRect().top - 16" in response.text
    assert "scrollIntoView" not in response.text
    assert '<body class="homepage-dashboard">' in response.text
    assert 'tabindex="0" role="region" aria-label="Lista de turnos"' in response.text
    assert "window.location.hash" in response.text
    assert "navigation?.type === 'back_forward'" in response.text


@pytest.mark.parametrize("offset", [-1, 1])
def test_other_months_do_not_auto_scroll(client, offset):
    today = date.today()
    year, month_index = divmod(today.year * 12 + today.month - 1 + offset, 12)

    response = client.get(f"/?year={year}&month={month_index + 1}")

    assert response.status_code == 200
    assert "scrollIntoView" not in response.text
    assert "list.scrollTo" not in response.text
    assert '<body class="homepage-dashboard">' in response.text


def test_my_days_does_not_auto_scroll(logged_in):
    response = logged_in.get("/my-days")

    assert response.status_code == 200
    assert "scrollIntoView" not in response.text
    assert "list.scrollTo" not in response.text
    assert 'class="homepage-dashboard"' not in response.text


def test_other_pages_keep_normal_page_scroll(logged_in):
    response = logged_in.get("/calendar")
    assert response.status_code == 200
    assert 'class="homepage-dashboard"' not in response.text


def test_homepage_scroll_styles_are_scoped(client):
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert ".homepage-dashboard{height:100vh;height:100dvh;overflow:hidden;display:flex;flex-direction:column}" in response.text
    assert ".homepage-dashboard .calendar-list{flex:1;min-height:0;overflow-y:auto;" in response.text
    assert ".homepage-dashboard .calendar-list>*{flex-shrink:0}" in response.text
