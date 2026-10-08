from datetime import date, time, timedelta
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.config import settings
from app.models import Assignment, Schedule, Team
from app.services.pdf import build_schedule_pdf


def download(client, schedule, start="2026-09-19", end="2026-12-26"):
    return client.get("/export/schedule.pdf", params={
        "schedule_id": schedule.id, "start_date": start, "end_date": end,
    })


def test_form_has_editable_dates_and_download_action(logged_in, schedule, monkeypatch):
    monkeypatch.setattr(settings, "root_path", "/crr")
    response = logged_in.get("/admin/schedules", params={"schedule_id": schedule.id})
    assert response.status_code == 200
    assert 'type="date" name="start_date"' in response.text
    assert 'type="date" name="end_date"' in response.text
    assert 'action="/crr/export/schedule.pdf"' in response.text
    assert "Descarregar PDF" in response.text
    assert "window.print" not in response.text
    assert f'value="{schedule.id}" selected' in response.text
    assert 'id="export-pdf"' in response.text
    assert f'/crr/admin/schedules?schedule_id={schedule.id}#export-pdf' in response.text


def test_old_admin_export_link_redirects_to_integrated_controls(logged_in, schedule):
    response = logged_in.get("/export/schedule", params={"schedule_id": schedule.id}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/schedules?schedule_id={schedule.id}#export-pdf"


def test_member_cannot_export_pdf(logged_in, db, admin, schedule):
    admin.is_admin = False
    db.commit()
    assert logged_in.get("/admin/schedules").status_code == 403
    response = logged_in.get("/export/schedule", params={"schedule_id": schedule.id})
    assert response.status_code == 403
    assert download(logged_in, schedule).status_code == 403
    response = logged_in.get("/")
    assert response.status_code == 200
    assert "Exportar PDF" not in response.text
    assert 'href="/export/schedule"' not in response.text


def test_both_export_routes_require_login(client, schedule):
    assert client.get("/export/schedule").status_code == 401
    assert download(client, schedule).status_code == 401


def test_pdf_is_one_a4_page_with_month_lists_and_inclusive_dates(logged_in, db, schedule):
    included = Team(name="João & Luís (Farragão)")
    excluded = Team(name="Não incluir")
    db.add_all([included, excluded])
    db.flush()
    db.add_all([
        Assignment(schedule_id=schedule.id, date=day, team_id=team.id, source=source)
        for day, team, source in [
            (date(2026, 9, 12), excluded, "generated"),
            (date(2026, 9, 19), included, "manual"),
            (date(2026, 12, 26), included, "swap"),
            (date(2027, 1, 2), excluded, "generated"),
        ]
    ])
    db.commit()
    response = download(logged_in, schedule)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "2026-09-19-2026-12-26.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    pdf = PdfReader(BytesIO(response.content))
    assert len(pdf.pages) == 1
    page = pdf.pages[0]
    assert float(page.mediabox.width) == pytest.approx(595.28, abs=0.1)
    assert float(page.mediabox.height) == pytest.approx(841.89, abs=0.1)
    text = page.extract_text()
    assert "João & Luís (Farragão)" in text
    assert "Não incluir" not in text
    headings = ["Setembro 2026", "Outubro 2026", "Novembro 2026", "Dezembro 2026"]
    assert all(heading in text for heading in headings)
    assert [text.index(heading) for heading in headings] == sorted(text.index(h) for h in headings)
    assert "19\nJoão" in text and "26\nJoão" in text
    assert "Sem atribuição" in text
    db.expire_all()
    preserved = db.scalars(select(Assignment).where(
        Assignment.schedule_id == schedule.id,
        Assignment.source.in_(["manual", "swap"]),
    ).order_by(Assignment.date)).all()
    assert [(row.team_id, row.source) for row in preserved] == [
        (included.id, "manual"), (included.id, "swap"),
    ]


def test_other_schedule_assignments_are_excluded(logged_in, db, schedule, team):
    other = Schedule(name="Outra escala", slug="other", schedule_type="fixed", weekdays="5")
    db.add(other)
    db.flush()
    db.add(Assignment(schedule_id=other.id, date=date(2026, 9, 19), team_id=team.id, source="manual"))
    db.commit()
    response = download(logged_in, schedule)
    text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
    assert team.name not in text
    assert other.name not in text


def test_full_daily_year_fits_one_page_without_losing_rows(logged_in, db, team):
    daily = Schedule(name="Noites de teste", slug="test-night", schedule_type="fixed", weekdays="0,1,2,3,4,5,6")
    db.add(daily)
    db.flush()
    from app.models import MonthlyPattern
    for day in range(1, 32):
        db.add(MonthlyPattern(schedule_id=daily.id, day_of_month=day, team_id=team.id))
    db.commit()
    response = download(logged_in, daily, "2028-01-01", "2028-12-31")
    pdf = PdfReader(BytesIO(response.content))
    assert len(pdf.pages) == 1
    assert pdf.pages[0].extract_text().count(team.name) == 366


@pytest.mark.parametrize(("start", "end", "message"), [
    ("2026-12-26", "2026-09-19", "data final"),
    ("2026-01-01", "2027-01-01", "12 meses"),
    ("1999-12-01", "2000-01-01", "2000 e 2100"),
])
def test_invalid_ranges_keep_form_values_and_show_error(logged_in, schedule, start, end, message):
    response = download(logged_in, schedule, start, end)
    assert response.status_code == 400
    assert message in response.text
    assert f'value="{start}"' in response.text and f'value="{end}"' in response.text
    assert 'id="export-pdf"' in response.text
    assert f'value="{schedule.id}" selected' in response.text


def test_malformed_date_is_rejected(logged_in, schedule):
    assert download(logged_in, schedule, "2026-02-30", "2026-03-01").status_code == 422


def test_single_day_and_empty_range_still_produce_pdf(logged_in, schedule):
    response = download(logged_in, schedule, "2026-09-19", "2026-09-19")
    text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
    assert text.count("Sem atribuição") == 1
    response = download(logged_in, schedule, "2026-09-20", "2026-09-20")
    assert "Sem turnos neste período." in PdfReader(BytesIO(response.content)).pages[0].extract_text()


def test_inactive_or_unknown_schedule_is_rejected(logged_in, db, schedule):
    schedule.is_active = False
    db.commit()
    assert download(logged_in, schedule).status_code == 404
    assert logged_in.get("/export/schedule", params={"schedule_id": 999999}).status_code == 404


def test_dense_long_names_wrap_and_remain_inside_page():
    schedule = Schedule(name="Noite", start_time=time(20, 30), end_time=time(0))
    team = Team(name="João " + "Carreira Ligeiro Farragão " * 4)
    first, last = date(2028, 1, 1), date(2028, 12, 31)
    rows = [Assignment(date=first + timedelta(days=index), team=team) for index in range(366)]
    pdf = PdfReader(BytesIO(build_schedule_pdf(schedule, rows, first, last)))
    assert len(pdf.pages) == 1
    page = pdf.pages[0]
    assert page.extract_text().count("João") == 366
    positions = []

    def record(text, cm, tm, font, size):
        if text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            positions.append((x, y))

    page.extract_text(visitor_text=record)
    assert all(0 <= x <= float(page.mediabox.width) and 0 <= y <= float(page.mediabox.height)
               for x, y in positions)
