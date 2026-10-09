import json

import boto3
from moto import mock_aws

NIGHT = {"day": "2024-11-18", "replay": True, "stats": {"events": 2, "counted": 0, "harm_total": 200.0, "first_seen": {}},
         "fires": [{"lat": 30.4, "lon": 74.1, "near": "Fazilka 12 km", "first_ist": "15:00", "scans": 3, "frp_peak": 40.0,
                    "pm25_kg": 900.0, "counted": False, "harm": 150.0, "source": "GK-2A"},
                   {"lat": 29.7, "lon": 75.6, "near": "Ratia 4 km", "first_ist": "16:00", "scans": 2, "frp_peak": 15.0,
                    "pm25_kg": 200.0, "counted": False, "harm": 50.0, "source": "GK-2A"}],
         "towns": [{"town": "Fazilka", "lat": 30.4, "lon": 74.03, "peak_ugm3": 51.2, "peak_ist": "Mon 18:00", "arrives_ist": "Mon 17:00"}],
         "frames": ["x"]}


@mock_aws
def test_tools_read_the_published_night(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("DATA_BUCKET", "data-b")
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="data-b")
    s3.put_object(Bucket="data-b", Key="results/20241118.json", Body=json.dumps(NIGHT))
    from saanjh import agent
    monkeypatch.setattr(agent, "s3", s3)
    agent._night.clear()
    a = agent.make_agent("2024-11-18")
    fire = a.tool.get_fire(rank=1, record_direct_tool_call=False)
    text = json.dumps(fire)
    assert "Fazilka 12 km" in text and "75.0" in text and '"lat"' not in text  # share 150/200, no coordinates
    assert "17:00" in json.dumps(a.tool.get_town(name="fazilka", record_direct_tool_call=False))
    assert "error" in json.dumps(a.tool.get_fire(rank=9, record_direct_tool_call=False))


def test_handler_validates_and_degrades(monkeypatch):
    from saanjh import agent
    assert agent.ask_handler({"queryStringParameters": {}})["statusCode"] == 400
    monkeypatch.setattr(agent, "make_agent", lambda day: (lambda q: f"echo: {q}"))
    r = agent.ask_handler({"queryStringParameters": {"rank": "3", "day": "../../x"}})
    assert json.loads(r["body"])["answer"] == "echo: Why is fire #3 ranked #3?"

    def down(day):
        raise RuntimeError("bedrock down")
    monkeypatch.setattr(agent, "make_agent", down)
    assert agent.ask_handler({"queryStringParameters": {"q": "hi"}})["statusCode"] == 503
