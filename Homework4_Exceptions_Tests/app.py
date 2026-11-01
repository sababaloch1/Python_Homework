from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from exceptions import CarbonLensException, S1_DataValidationError

app = Flask(__name__)
# Use SQLite for tests, but in production it would use MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
db = SQLAlchemy(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    course = db.Column(db.String(80), nullable=False)

with app.app_context():
    db.create_all()

# Error Handler
@app.errorhandler(CarbonLensException)
def handle_carbonlens_error(error):
    return jsonify({"error": error.__class__.__name__, "message": error.message}), error.status_code

@app.route('/students', methods=['GET'])
def get_students():
    students = Student.query.all()
    return jsonify([{"id": s.id, "name": s.name, "course": s.course} for s in students])

@app.route('/students', methods=['POST'])
def add_student():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("course"):
        raise S1_DataValidationError("Missing name or course in request", status_code=400)
    
    new_student = Student(name=data["name"], course=data["course"])
    db.session.add(new_student)
    db.session.commit()
    return jsonify({"message": "Student added successfully"}), 201