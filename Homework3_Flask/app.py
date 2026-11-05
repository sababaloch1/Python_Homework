from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# Connect to MySQL running in Docker
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:rootpassword@localhost:3306/homework_db'
db = SQLAlchemy(app)

# Define a simple database model
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    course = db.Column(db.String(80), nullable=False)

# Create tables and add a sample record on startup
with app.app_context():
    db.create_all()
    if not Student.query.first():
        db.session.add(Student(name="Saba Brahmani", course="Digital Transformation"))
        db.session.commit()

# API Endpoint to output data from MySQL
@app.route('/students', methods=['GET'])
def get_students():
    students = Student.query.all()
    result = [{"id": s.id, "name": s.name, "course": s.course} for s in students]
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, port=5000)