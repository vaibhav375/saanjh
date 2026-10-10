"""Both Lambda handlers end to end against mocked S3/SNS, using cached GK-2A scans of 18 Nov 2024.
Skipped when the cache is absent (fresh clone)."""
import json
import os

import boto3
import pandas as pd
import pytest
from moto import mock_aws

DAY = "2024-11-18"
CACHE = os.path.join("data", "gk2a", "1178_1375_615_905", "sw038_202411181030.npy")
pytestmark = pytest.mark.skipif(not os.path.exists(CACHE), reason="needs cached GK-2A scans")


@mock_aws
def test_replay_day_then_model(monkeypatch):
    monkeypatch.setenv("SAANJH_DATA", os.path.abspath("data"))
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    for b in ("data-b", "site-b"):
        boto3.client("s3").create_bucket(Bucket=b)
    from saanjh import aws, gk2a, pipeline
    monkeypatch.setattr(pipeline, "ENSEMBLE", 2)  # keep the test fast; the live system runs 8 members
    monkeypatch.setattr(aws, "s3", boto3.client("s3"))
    monkeypatch.setattr(aws, "BUCKET", "data-b")
    monkeypatch.setattr(aws, "read_scan", gk2a.cached_bt)
    v = pd.read_csv("data/firms/viirs_snpp_2024_punjab_both_octnov.csv")
    aws.s3.put_object(Bucket="data-b", Key="viirs/punjab_both.csv", Body=v.to_csv(index=False))

    r = aws.detect_handler({"day": DAY, "step_min": 60})
    assert r["scans"] >= 8 and r["detections"] > 100

    out = aws.model_handler({"day": DAY, "replay": True})
    assert out["events"] > 100 and out["uncounted_energy_share"] > 0.5
    res = json.loads(aws.s3.get_object(Bucket="data-b", Key="results/20241118.json")["Body"].read())
    assert len(res["fires"]) == 50 and res["fires"][0]["harm"] >= res["fires"][-1]["harm"]
    assert len(res["frames"]) > 24


def test_live_message_parsing(monkeypatch):
    from saanjh import aws
    seen = []
    monkeypatch.setattr(aws, "_detect", lambda t: seen.append(t) or None)
    key = "AMI/L1B/FD/202610/09/11/gk2a_ami_le1b_sw038_fd020ge_202610091100.nc"
    other = "AMI/L1B/FD/202610/09/11/gk2a_ami_le1b_vi006_fd005ge_202610091100.nc"
    msg = lambda k: {"body": json.dumps({"Message": json.dumps({"Records": [{"s3": {"object": {"key": k}}}]})})}
    aws.detect_handler({"Records": [msg(key), msg(other)]})
    assert [t.strftime("%Y%m%d%H%M") for t in seen] == ["202610091100"]


@mock_aws
def test_site_serves_page_live_json_and_replays(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    from saanjh import aws
    s3 = boto3.client("s3")
    for b in ("data-b", "site-b"):
        s3.create_bucket(Bucket=b)
    s3.put_object(Bucket="site-b", Key="tonight.json", Body=b'{"live": 1}')
    s3.put_object(Bucket="data-b", Key="results/20241118.json", Body=b'{"replay": 1}')
    monkeypatch.setattr(aws, "s3", s3)
    monkeypatch.setattr(aws, "BUCKET", "data-b")
    monkeypatch.setattr(aws, "SITE", "site-b")
    assert "<title>Saanjh" in aws.site_handler({"rawPath": "/"})["body"]
    assert aws.site_handler({"rawPath": "/tonight.json"})["body"] == '{"live": 1}'
    r = aws.site_handler({"rawPath": "/tonight.json", "queryStringParameters": {"day": "2024-11-18"}})
    assert r["body"] == '{"replay": 1}'
    assert aws.site_handler({"rawPath": "/tonight.json", "queryStringParameters": {"day": "../x"}})["body"] == '{"live": 1}'
    assert aws.site_handler({"rawPath": "/../template.yaml"})["statusCode"] == 404


@mock_aws
def test_briefing_pdf_for_a_district(monkeypatch):
    import base64
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    from saanjh import aws
    s3 = boto3.client("s3")
    for b in ("data-b", "site-b"):
        s3.create_bucket(Bucket=b)
    s3.put_object(Bucket="site-b", Key="tonight.json", Body=open("site/tonight.json", "rb").read())
    s3.put_object(Bucket="site-b", Key="plan.json", Body=open("site/plan.json", "rb").read())
    monkeypatch.setattr(aws, "s3", s3)
    monkeypatch.setattr(aws, "BUCKET", "data-b")
    monkeypatch.setattr(aws, "SITE", "site-b")
    r = aws.site_handler({"rawPath": "/briefing.pdf", "queryStringParameters": {"district": "sangrur"}})
    assert r["statusCode"] == 200 and r["headers"]["Content-Type"] == "application/pdf"
    assert base64.b64decode(r["body"])[:5] == b"%PDF-"
    assert aws.site_handler({"rawPath": "/briefing.pdf", "queryStringParameters": {"district": "Atlantis"}})["statusCode"] == 404
