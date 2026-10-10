from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app


class BrandResources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stylesheets: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href") or "")
        if tag == "img":
            self.images.append(attributes.get("src") or "")


@pytest.mark.parametrize("prefix", ["", "/crr"])
def test_login_brand_resources_are_public_and_work_under_root_path(db: Session, prefix: str) -> None:
    with TestClient(app, root_path=prefix) as client:
        response = client.get(f"{prefix}/login")
        assert response.status_code == 200
        resources = BrandResources()
        resources.feed(response.text)
        paths = [url.removeprefix("http://testserver") for url in resources.stylesheets]
        assert paths
        for path in paths:
            stylesheet = client.get(path)
            assert stylesheet.status_code == 200
            assert stylesheet.headers["content-type"].startswith("text/css")
        assert resources.images
        for url in resources.images:
            assert f"{prefix}/brand/assets/logo.png" in url
            image = client.get(url)
            assert image.status_code == 200
            assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
        favicon = client.get(f"{prefix}/brand/assets/favicon.png")
        assert favicon.status_code == 200
        assert favicon.content.startswith(b"\x89PNG\r\n\x1a\n")
