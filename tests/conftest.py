import pytest
from fastapi.testclient import TestClient
from autoreadpaper.store import init
from autoreadpaper.api import app
from autoreadpaper.worker import STOP

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('ARP_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.delenv('ARP_API_KEY',raising=False)
    STOP.clear();init()

@pytest.fixture
def client():
    with TestClient(app) as c:yield c

@pytest.fixture
def pdf_bytes():
    import pymupdf
    doc=pymupdf.open()
    p=doc.new_page()
    p.insert_text((50,60),'Test Research Paper: Robot Navigation',fontsize=16)
    p.insert_textbox((50,100,500,250),'We evaluate a visual navigation method on 100 simulation episodes. The method achieves 85 percent success. This is a synthetic test fixture and not a real research finding. Figure 1 describes a toy navigation pipeline.',fontsize=12)
    p.draw_rect((50,300,400,400),color=(.5,.3,.8))
    p.insert_text((60,350),'Visual input -> Navigation -> Action',fontsize=14)
    p.insert_text((50,430),'Figure 1. Toy navigation pipeline for software testing.',fontsize=11)
    data=doc.tobytes();doc.close();return data
