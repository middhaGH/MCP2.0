import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
from werkzeug.utils import secure_filename
import openpyxl
from sqlalchemy.exc import SQLAlchemyError

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', filename='app.log', filemode='a')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jobs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'your_secret_key_here'

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(200), nullable=False)
    resume_used = db.Column(db.String(200))
    date_applied = db.Column(db.String(20))
    status = db.Column(db.String(50))
    interview_details = db.Column(db.Text)
    comments = db.Column(db.Text)
    link = db.Column(db.String(300))

    def __repr__(self):
        return f"<Job {self.company} - {self.position}>"

# Add logging to track application flow
logging.info("Starting Flask application")

@app.route('/')
def index():
    return redirect('/jobs')

@app.route('/jobs', methods=['GET', 'POST'])
def jobs():
    try:
        if request.method == 'POST':
            logging.info("Received POST request to add a new job")
            new_job = Job(
                company=request.form['company'],
                position=request.form['position'],
                resume_used=request.form.get('resume_used'),
                date_applied=request.form.get('date_applied'),
                status=request.form.get('status'),
                interview_details=request.form.get('interview_details'),
                comments=request.form.get('comments'),
                link=request.form.get('link')
            )
            db.session.add(new_job)
            db.session.commit()
            logging.info(f"Added new job: {new_job}")
            return redirect(url_for('jobs'))

        logging.info("Fetching all jobs from the database")
        all_jobs = Job.query.all()
        logging.debug(f"Retrieved jobs: {all_jobs}")
        return render_template('jobs.html', jobs=all_jobs)
    except SQLAlchemyError as e:
        logging.error(f"Database error: {e}")
        flash(f"Database error: {e}")
        return render_template('jobs.html', jobs=[])

@app.route('/edit_job/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)

    if request.method == 'POST':
        # Update the job details
        job.company = request.form['company']
        job.position = request.form['position']
        job.resume_used = request.form.get('resume_used')
        job.date_applied = request.form.get('date_applied')
        job.status = request.form.get('status')
        job.interview_details = request.form.get('interview_details')
        job.comments = request.form.get('comments')
        job.link = request.form.get('link')

        db.session.commit()
        return redirect(url_for('jobs'))

    return render_template('jobs.html', jobs=Job.query.all(), edit_job=job)

@app.route('/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    return redirect(url_for('jobs'))

@app.route('/upload', methods=['POST'])
def upload():
    logging.info("Received file upload request")
    if 'file' not in request.files:
        logging.warning("No file part in the request")
        flash('No file part in the request')
        return redirect(url_for('jobs'))

    file = request.files['file']

    if file.filename == '':
        logging.warning("No file selected for upload")
        flash('No selected file')
        return redirect(url_for('jobs'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logging.info(f"File saved to {filepath}")

        try:
            if filename.endswith('.csv'):
                data = pd.read_csv(filepath)
            else:
                data = pd.read_excel(filepath)

            logging.info("Validating column headers")
            required_columns = {'company', 'position', 'resume used', 'date applied', 'status', 'interview details', 'comments', 'link'}
            file_columns = set(data.columns.str.strip().str.lower())

            if not required_columns.issubset(file_columns):
                missing_columns = required_columns - file_columns
                logging.warning(f"Missing required columns: {missing_columns}")
                flash(f"Missing required columns: {missing_columns}")
                return redirect(url_for('jobs'))

            logging.info("Normalizing column names and processing rows")
            data.columns = data.columns.str.strip().str.lower()

            # Handle column renaming and ignore unnecessary columns
            column_mapping = {
                'compay applied': 'company',
                'position applied': 'position',
                'resume used': 'resume used',
                'date applied': 'date applied',
                'status': 'status',
                'interview details': 'interview details',
                'comments': 'comments',
                'link': 'link'
            }
            data.rename(columns=column_mapping, inplace=True)

            # Drop unnecessary columns
            data = data[[col for col in column_mapping.values() if col in data.columns]]

            for _, row in data.iterrows():
                new_job = Job(
                    company=row.get('company', ''),
                    position=row.get('position', ''),
                    resume_used=row.get('resume used', ''),
                    date_applied=row.get('date applied', ''),
                    status=row.get('status', ''),
                    interview_details=row.get('interview details', ''),
                    comments=row.get('comments', ''),
                    link=row.get('link', '')
                )
                db.session.add(new_job)
                logging.info(f"Added job from file: {new_job}")

            db.session.commit()
            logging.info("File processed and data committed to the database")
            flash('File uploaded and data imported successfully!')
            return redirect(url_for('jobs'))
        except Exception as e:
            logging.error(f"Error processing file: {e}")
            flash(f"Error processing file: {e}")

    return redirect(url_for('jobs'))

@app.route('/validate_columns', methods=['GET'])
def validate_columns():
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'JobApplications.xlsx')

    if not os.path.exists(filepath):
        return "Excel file not found.", 404

    # Read column names from the Excel sheet
    workbook = openpyxl.load_workbook(filepath)
    sheet = workbook.active
    excel_columns = [cell.value.strip().lower() for cell in sheet[1] if cell.value]

    # Define expected column names from the database
    expected_columns = {'company', 'position', 'resume used', 'date applied', 'status', 'interview details', 'comments', 'link'}

    # Compare columns
    missing_columns = expected_columns - set(excel_columns)
    extra_columns = set(excel_columns) - expected_columns

    if missing_columns or extra_columns:
        return f"Missing columns: {missing_columns}, Extra columns: {extra_columns}", 400

    return "Column names are aligned.", 200

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx'}

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)