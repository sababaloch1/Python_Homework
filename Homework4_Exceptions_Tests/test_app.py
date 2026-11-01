import pytest
from app import app, db, Student

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()

# --- Tests 1-5: Database Model ---
def test_1_db_model_creation(client):
    with app.app_context():
        s = Student(name="Saba", course="MDT")
        db.session.add(s)
        db.session.commit()
        assert s.id is not None

def test_2_db_model_query_empty(client):
    with app.app_context():
        assert Student.query.count() == 0

def test_3_db_model_name_required(client):
    with app.app_context():
        with pytest.raises(Exception):
            db.session.add(Student(name=None, course="MDT"))
            db.session.commit()

def test_4_db_model_course_required(client):
    with app.app_context():
        with pytest.raises(Exception):
            db.session.add(Student(name="Tuba", course=None))
            db.session.commit()

def test_5_db_model_string_length(client):
    with app.app_context():
        s = Student(name="A"*80, course="MDT")
        db.session.add(s)
        db.session.commit()
        assert len(s.name) == 80

# --- Tests 6-10: API Endpoints ---
def test_6_api_get_empty(client):
    res = client.get('/students')
    assert res.status_code == 200
    assert res.json == []

def test_7_api_post_student(client):
    res = client.post('/students', json={"name": "Sameer", "course": "MDT"})
    assert res.status_code == 201
    assert res.json["message"] == "Student added successfully"

def test_8_api_get_after_post(client):
    client.post('/students', json={"name": "Mustafa", "course": "MDT"})
    res = client.get('/students')
    assert len(res.json) == 1
    assert res.json[0]["name"] == "Mustafa"

def test_9_api_response_content_type(client):
    res = client.get('/students')
    assert res.headers["Content-Type"] == "application/json"

def test_10_api_invalid_route(client):
    res = client.get('/unknown-endpoint')
    assert res.status_code == 404

# --- Tests 11-15: Exception Handling (S1 Errors) ---
def test_11_error_missing_name(client):
    res = client.post('/students', json={"course": "MDT"})
    assert res.status_code == 400
    assert res.json["error"] == "S1_DataValidationError"

def test_12_error_missing_course(client):
    res = client.post('/students', json={"name": "Saba"})
    assert res.status_code == 400
    assert res.json["error"] == "S1_DataValidationError"

def test_13_error_empty_json(client):
    res = client.post('/students', json={})
    assert res.status_code == 400

def test_14_error_no_json(client):
    res = client.post('/students')
    assert res.status_code in [400, 415]

def test_15_error_custom_message(client):
    res = client.post('/students', json={})
    assert "Missing name or course" in res.json["message"]