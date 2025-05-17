import os
import json
import google.generativeai as genai
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import nltk
from nltk.corpus import wordnet
from difflib import SequenceMatcher
import logging
from markupsafe import Markup
from datetime import datetime

from interview_logic import generate_question, evaluate_answer

try:
    wordnet.synsets('test')
except:
    nltk.download('wordnet')

app = Flask(__name__)
app.secret_key = 'ton_secret_key' 

# Add template context processor
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Add the nl2br filter
@app.template_filter('nl2br')
def nl2br(value):
    """Convert newlines to <br> tags"""
    if not value:
        return ""
    return Markup(value.replace('\n', '<br>'))

# Configuration pour les uploads de fichiers
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max

# Set your API key
os.environ["GOOGLE_API_KEY"] = "your_api_key_here"  # Replace with your actual API key
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

# Load model
model = genai.GenerativeModel("models/gemini-1.5-pro")

def resumes_details(resume):
    # Prompt with detailed request
    prompt = f"""
    You are a resume parsing assistant. Given the following resume text, extract all the important details and return them in a well-structured JSON format.

    The resume text:
    {resume}

    Extract and include the following:
    - Full Name
    - Contact Number
    - Email Address
    - Location
    - Skills (Technical and Non-Technical, separately if possible)
    - Education
    - Work Experience (including company name, role, and responsibilities)
    - Certifications
    - Languages spoken
    - Suggested Resume Category
    - Recommended Job Roles

    Return the response in JSON format.
    """

    # Generate response from the model
    response = model.generate_content(prompt).text
    return response


def normalize_text(text):
    """Normalize text for comparison"""
    if not isinstance(text, str):
        return ""
    normalized = text.lower().strip()
    return f" {normalized} " if len(normalized) == 1 else normalized

def is_similar(str1, str2, threshold=0.6):
    """Check if two strings are similar using sequence matcher"""
    str1, str2 = normalize_text(str1), normalize_text(str2)
    if len(str1.strip()) == 1 or len(str2.strip()) == 1:
        return str1.strip() == str2.strip()
    ratio = SequenceMatcher(None, str1, str2).ratio()
    return ratio >= threshold

def skill_similarity(skill1, skill2):
    """Calculate semantic similarity using WordNet"""
    if is_similar(skill1, skill2):
        return 1.0
    synsets1 = wordnet.synsets(skill1)
    synsets2 = wordnet.synsets(skill2)
    if synsets1 and synsets2:
        return synsets1[0].wup_similarity(synsets2[0]) or 0
    return 0

def find_matching_skills(offer_skills, resume_skills, similarity_threshold=0.8):
    """Find matching skills using both string and semantic similarity"""
    matches = set()
    similarities = []
    
    for offer_skill in offer_skills:
        offer_skill = normalize_text(offer_skill)
        best_match_score = 0
        
        for resume_skill in resume_skills:
            resume_skill = normalize_text(resume_skill)
            
            if len(offer_skill.strip()) == 1 or len(resume_skill.strip()) == 1:
                if offer_skill.strip() == resume_skill.strip():
                    matches.add(offer_skill.strip())
                    similarities.append(1.0)
                continue
            
            sim_score = max(
                skill_similarity(offer_skill, resume_skill),
                SequenceMatcher(None, offer_skill, resume_skill).ratio()
            )
            
            if sim_score > best_match_score:
                best_match_score = sim_score
        
        if best_match_score >= similarity_threshold:
            matches.add(offer_skill.strip())
            similarities.append(best_match_score)
    
    return matches, sum(similarities) / max(len(similarities), 1)

def normalize_language(lang):
    """Normalize language names"""
    lang_map = {
        'français': ['french', 'français', 'francais', 'french (fluent)', 'français (courant)'],
        'anglais': ['english', 'anglais', 'english (fluent)', 'anglais (courant)'],
        'allemand': ['german', 'allemand', 'german (fluent)', 'allemand (courant)'],
        'espagnol': ['spanish', 'espagnol', 'spanish (fluent)', 'espagnol (courant)']
    }
    lang = normalize_text(lang)
    for norm_lang, variants in lang_map.items():
        if any(variant in lang for variant in variants):
            return norm_lang
    return lang

def get_db_connection():
    """Create database connection"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_score(user_id, offer_id):
    """Calculate matching score between offer and application"""
    conn = None
    try:
        conn = get_db_connection()
        
        offer = conn.execute("""
            SELECT skills, languages 
            FROM job_offers 
            WHERE id = ?
        """, (offer_id,)).fetchone()

        if not offer:
            logging.warning(f"Offer with id {offer_id} not found")
            return 0

        application = conn.execute("""
            SELECT parsed_cv 
            FROM applications 
            WHERE user_id = ? AND offer_id = ?
        """, (user_id, offer_id)).fetchone()

        if not application:
            logging.warning(f"No application found for user {user_id} and offer {offer_id}")
            return 0

        # Parse data
        resume_data = json.loads(application['parsed_cv'])
        
        # Extract and normalize skills
        offer_skills = [skill.strip() for skill in offer['skills'].split(',')]
        offer_languages = [lang.strip() for lang in offer['languages'].split(',')]
        
        resume_skills = (
            resume_data.get('skills', {}).get('technical', []) +
            resume_data.get('skills', {}).get('non_technical', [])
        )
        resume_languages = resume_data.get('languages', [])

        # Calculate matches with improved similarity scoring
        matching_skills, skills_similarity = find_matching_skills(offer_skills, resume_skills)
        matching_languages = {normalize_language(lang) for lang in resume_languages} & {normalize_language(lang) for lang in offer_languages}

        # Calculate weighted score
        skills_weight = 0.7
        languages_weight = 0.3

        skills_score = len(matching_skills) / max(len(offer_skills), 1)
        languages_score = len(matching_languages) / max(len(offer_languages), 1)

        final_score = (skills_score * skills_weight + languages_score * languages_weight) * 10

        # Print detailed results for debugging
        print("\nMatching Analysis:")
        print(f"Required Skills: {offer_skills}")
        print(f"Candidate Skills: {resume_skills}")
        print(f"Matching Skills: {matching_skills}")
        print(f"Skills Similarity Score: {skills_score:.2f}")
        print(f"\nRequired Languages: {offer_languages}")
        print(f"Candidate Languages: {resume_languages}")
        print(f"Matching Languages: {matching_languages}")
        print(f"\nFinal Score: {round(final_score, 2)}/10")

        return round(final_score, 2)

    except Exception as e:
        logging.error(f"Error calculating score: {e}")
        return 0
    
    finally:
        if conn:
            conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Créez le dossier uploads s'il n'existe pas
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Décorateur pour protéger les routes
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login', next=request.url))
            if role is not None and session['role'] != role:
                return render_template('403.html'), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def view_applications(offer_id):
    """Get applications with calculated scores and matches for an offer"""
    conn = get_db_connection()
    applications = []
    
    try:
        # Get offer details
        offer = conn.execute('SELECT * FROM job_offers WHERE id = ? AND created_by = ?', 
                           (offer_id, session['user_id'])).fetchone()
        
        if not offer:
            return None, []

        # Get all applications for this offer with chatbot results
        candidates = conn.execute('''
            SELECT a.*, u.email, u.nom, u.prenom 
            FROM applications a 
            JOIN users u ON a.user_id = u.id 
            WHERE a.offer_id = ?
        ''', (offer_id,)).fetchall()

        for candidate in candidates:
            try:
                resume_data = json.loads(candidate['parsed_cv'])
                
                # Calculate matches
                offer_skills = [skill.strip() for skill in offer['skills'].split(',')]
                offer_languages = [lang.strip() for lang in offer['languages'].split(',')]
                
                resume_skills = (
                    resume_data.get('skills', {}).get('technical', []) +
                    resume_data.get('skills', {}).get('non_technical', [])
                )
                resume_languages = resume_data.get('languages', [])

                # Find matches
                matching_skills, _ = find_matching_skills(offer_skills, resume_skills)
                matching_languages = {normalize_language(lang) for lang in resume_languages} & {normalize_language(lang) for lang in offer_languages}

                applications.append({
                    'email': candidate['email'],
                    'nom': candidate['nom'],
                    'prenom': candidate['prenom'],
                    'cv_path': candidate['cv_path'],
                    'score': candidate['score'],
                    'status': candidate['status'],
                    'chatbot_score': candidate['chatbot_score'],
                    'chatbot_feedback': candidate['chatbot_feedback'],
                    'matched_skills': list(matching_skills),
                    'matched_languages': list(matching_languages)
                })

            except Exception as e:
                print(f"Error processing candidate {candidate['user_id']}: {e}")
                continue

        # Sort by total score (CV + chatbot if available)
        def get_total_score(app):
            cv_score = app['score'] or 0
            chatbot_score = app['chatbot_score'] or 0
            if app['status'] == 'completed':
                return (cv_score + chatbot_score) / 2
            return cv_score

        applications.sort(key=get_total_score, reverse=True)
        return offer, applications

    except Exception as e:
        print(f"Error in view_applications: {e}")
        return None, []
    finally:
        conn.close()

@app.route('/view_applications/<int:offer_id>')
@login_required(role='admin')
def view_applications_route(offer_id):
    offer, candidates = view_applications(offer_id)
    if not offer:
        flash('Offre non trouvée ou accès non autorisé', 'error')
        return redirect(url_for('admin_dashboard'))
    return render_template('view_applications.html', offer=offer, candidates=candidates)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        nom = request.form['nom']
        prenom = request.form['prenom']
        telephone = request.form['telephone']

        conn = get_db_connection()
        try:
            # Vérifier si l'email existe déjà
            existing_user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

            if existing_user is not None:
                flash('Cet email est déjà enregistré.', 'error')
                return render_template('register.html')

            hashed_password = generate_password_hash(password)
            
            # Modifié la requête pour inclure les nouveaux champs
            conn.execute('''
                INSERT INTO users (email, password, role, nom, prenom, telephone) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (email, hashed_password, role, nom, prenom, telephone))
            
            conn.commit()
            flash('Inscription réussie, veuillez vous connecter.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f'Erreur lors de l\'inscription: {str(e)}', 'error')
            return render_template('register.html')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['email'] = user['email']
            flash('Connexion réussie !', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('candidat_dashboard'))
        else:
            flash('Email ou mot de passe incorrect.', 'error')
            return render_template('login.html')

    return render_template('login.html')

@app.route('/admin')
@login_required(role='admin')
def admin_dashboard():
    conn = get_db_connection()
    try:
        # Get all offers with application counts by status
        offers = conn.execute('''
            SELECT o.*, 
                COUNT(DISTINCT a.user_id) as total_applications,
                SUM(CASE WHEN a.status = 'pending' THEN 1 ELSE 0 END) as pending_count,
                SUM(CASE WHEN a.status = 'chatbot-interview' THEN 1 ELSE 0 END) as interview_count,
                SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) as completed_count
            FROM job_offers o
            LEFT JOIN applications a ON o.id = a.offer_id
            WHERE o.created_by = ?
            GROUP BY o.id
        ''', (session['user_id'],)).fetchall()
        
        # Convert to list of dicts with application counts
        offers_with_counts = []
        for offer in offers:
            offer_dict = dict(offer)
            offer_dict['application_counts'] = {
                'total': offer['total_applications'] or 0,
                'pending': offer['pending_count'] or 0,
                'interview': offer['interview_count'] or 0,
                'completed': offer['completed_count'] or 0
            }
            offers_with_counts.append(offer_dict)
            
        return render_template('admin_dashboard.html', offers=offers_with_counts)
    except Exception as e:
        flash(f'Erreur: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        conn.close()

@app.route('/candidat')
@login_required(role='candidat')
def candidat_dashboard():
    conn = get_db_connection()
    try:
        # Get all job offers
        offers = conn.execute('SELECT * FROM job_offers').fetchall()
        
        # Get all applications with scores and status for current user
        applications = conn.execute('''
            SELECT offer_id, score, status, chatbot_score, chatbot_feedback 
            FROM applications 
            WHERE user_id = ?
        ''', (session['user_id'],)).fetchall()

        # Create dictionaries to map offer_id to various attributes
        offer_scores = {app['offer_id']: app['score'] for app in applications}
        application_statuses = {app['offer_id']: app['status'] for app in applications}
        chatbot_scores = {app['offer_id']: app['chatbot_score'] for app in applications if app['chatbot_score']}
        chatbot_feedback = {app['offer_id']: app['chatbot_feedback'] for app in applications if app['chatbot_feedback']}

        return render_template('candidat_dashboard.html', 
                            offers=offers,
                            offer_scores=offer_scores,
                            application_statuses=application_statuses,
                            chatbot_scores=chatbot_scores,
                            chatbot_feedback=chatbot_feedback)
    except Exception as e:
        flash(f'Erreur: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/create_offer', methods=['GET', 'POST'])
@login_required(role='admin')
def create_offer():
    if request.method == 'POST':
        company_name = request.form['company_name']
        title = request.form['title']
        description = request.form['description']
        skills = request.form['skills']
        experience = request.form.get('experience', 0)  # Utilisez .get() pour éviter les erreurs
        education = request.form.get('education', 'aucun')
        languages = request.form.get('languages', 'Aucune')

        # Debugging: Affichez les valeurs récupérées
        print(f"Company Name: {company_name}")
        print(f"Title: {title}")
        print(f"Description: {description}")
        print(f"Skills: {skills}")
        print(f"Experience: {experience}")
        print(f"Education: {education}")
        print(f"Languages: {languages}")

        # Vérifiez que les champs ne sont pas vides
        if not experience:
            experience = 0  # Valeur par défaut
        if not education:
            education = 'aucun'  # Valeur par défaut
        if not languages:
            languages = 'Aucune'  # Valeur par défaut

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO job_offers (company_name, title, description, skills, experience, education, languages, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (company_name, title, description, skills, experience, education, languages, session['user_id']))
        conn.commit()
        conn.close()

        flash('Offre créée avec succès', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('create_offer.html')

def normalize_path(path):
    """Convert Windows path separators to forward slashes"""
    return path.replace('\\', '/')

@app.route('/apply/<int:offer_id>', methods=['GET', 'POST'])
@login_required(role='candidat')
def apply(offer_id):
    if request.method == 'POST':
        if 'cv' not in request.files:
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)

        file = request.files['cv']

        if file.filename == '':
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            try:
                # Save CV file
                filename = secure_filename(f"user_{session['user_id']}_offer_{offer_id}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Normalize filepath for database storage
                db_filepath = normalize_path(filepath)

                # Extract text from the PDF
                text = ""
                reader = PdfReader(filepath)
                for page in reader.pages:
                    text += page.extract_text()

                # Get resume details from the model
                response = resumes_details(text)
                print(response)

                # Clean the response
                response_clean = response.replace("```json", "").replace("```", "").strip()
                resume_data = json.loads(response_clean)

                # Fetch offer details
                conn = get_db_connection()
                offer = conn.execute('SELECT * FROM job_offers WHERE id = ?', (offer_id,)).fetchone()
                if not offer:
                    flash('Offre non trouvée.', 'error')
                    conn.close()
                    return redirect(url_for('candidat_dashboard'))

                #

                # Save to database
                score = calculate_score(session['user_id'], offer_id)
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    # Insert application with normalized path
                    cursor.execute('''
                        INSERT INTO applications (user_id, offer_id, cv_path, score, parsed_cv, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (session['user_id'], offer_id, db_filepath, 0, json.dumps(resume_data), 'pending'))
                    conn.commit()
                    #update score after insertion

                    score = calculate_score(session['user_id'], offer_id)
                    cursor.execute('''
                        UPDATE applications 
                        SET score = ? 
                        WHERE user_id = ? AND offer_id = ?
                    ''', (score, session['user_id'], offer_id))


                    conn.commit()

                    # Update status based on score
                    update_application_status(session['user_id'], offer_id, score)

                    flash('Votre candidature a été envoyée avec succès!', 'success')
                    return redirect(url_for('candidat_dashboard'))

                except sqlite3.Error as e:
                    conn.rollback()
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    flash(f'Erreur lors de l\'enregistrement: {str(e)}', 'error')
                finally:
                    if conn:
                        conn.close()

            except Exception as e:
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash(f'Erreur lors du traitement du CV: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Seuls les fichiers PDF sont autorisés', 'error')

    return render_template('apply.html', offer_id=offer_id)

@app.route('/edit_offer/<int:id>', methods=['GET', 'POST'])
@login_required(role='admin')
def edit_offer(id):
    conn = get_db_connection()
    try:
        # Verify offer belongs to admin
        offer = conn.execute('''
            SELECT * FROM job_offers 
            WHERE id = ? AND created_by = ?
        ''', (id, session['user_id'])).fetchone()

        if not offer:
            flash('Offre non trouvée ou accès non autorisé', 'error')
            return redirect(url_for('admin_dashboard'))

        if request.method == 'POST':
            # Get form data with defaults for optional fields
            title = request.form['title']
            description = request.form['description']
            skills = request.form['skills']
            company_name = request.form['company_name']
            experience = request.form.get('experience', 0)
            education = request.form.get('education', 'aucun')
            languages = request.form.get('languages', '')
            location = request.form.get('location', '')
            salary = request.form.get('salary', '')
            contract_type = request.form.get('contract_type', '')

            conn.execute('''
                UPDATE job_offers 
                SET title = ?, 
                    description = ?, 
                    skills = ?, 
                    company_name = ?,
                    experience = ?,
                    education = ?,
                    languages = ?,
                    location = ?,
                    salary = ?,
                    contract_type = ?
                WHERE id = ?
            ''', (title, description, skills, company_name, 
                  experience, education, languages, location,
                  salary, contract_type, id))
            conn.commit()
            flash('Offre mise à jour avec succès', 'success')
            return redirect(url_for('admin_dashboard'))

        return render_template('edit_offer.html', offer=offer)
    except Exception as e:
        flash(f'Erreur lors de la modification: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))
    finally:
        conn.close()

@app.route('/delete_offer/<int:id>', methods=['POST'])
@login_required(role='admin')
def delete_offer(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM job_offers WHERE id = ?', (id,))
    conn.commit()
    conn.close()

    flash('Offre supprimée avec succès', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/start_interview/<int:offer_id>')
@login_required(role='candidat')
def start_interview(offer_id):
    conn = get_db_connection()
    try:
        # Get the application and check if interview is available
        application = conn.execute('''
            SELECT * FROM applications 
            WHERE user_id = ? AND offer_id = ?
        ''', (session['user_id'], offer_id)).fetchone()
        
        if not application:
            flash('Application non trouvée', 'error')
            return redirect(url_for('candidat_dashboard'))
            
        if application['status'] != 'chatbot-interview':
            flash('Entretien non disponible pour cette offre. Score minimum requis non atteint.', 'error')
            return redirect(url_for('candidat_dashboard'))

        # Update application status to indicate interview has started
        conn.execute('''
            UPDATE applications 
            SET status = 'interview-in-progress' 
            WHERE user_id = ? AND offer_id = ?
        ''', (session['user_id'], offer_id))
        conn.commit()
            
        return redirect(url_for('chatbot_interview', offer_id=offer_id))
    except Exception as e:
        flash(f'Erreur: {str(e)}', 'error')
        return redirect(url_for('candidat_dashboard'))
    finally:
        conn.close()

@app.route('/chatbot_interview/<int:offer_id>', methods=['GET', 'POST'])
@login_required(role='candidat')
def chatbot_interview(offer_id):
    MAX_QUESTIONS = 6  # Maximum number of questions to ask
    conn = get_db_connection()
    try:
        # Get the job offer details with required skills
        offer = conn.execute('''
            SELECT * FROM job_offers 
            WHERE id = ?
        ''', (offer_id,)).fetchone()

        if not offer:
            flash('Offre non trouvée', 'error')
            return redirect(url_for('candidat_dashboard'))

        # Get the candidate's application and parsed CV data
        application = conn.execute('''
            SELECT * FROM applications 
            WHERE user_id = ? AND offer_id = ?
        ''', (session['user_id'], offer_id)).fetchone()

        if not application:
            flash('Application non trouvée', 'error')
            return redirect(url_for('candidat_dashboard'))

        # Parse the skills from the offer and CV
        offer_skills = [skill.strip() for skill in offer['skills'].split(',')]
        
        try:
            parsed_cv = json.loads(application['parsed_cv'])
            candidate_skills = (
                parsed_cv.get('skills', {}).get('technical', []) +
                parsed_cv.get('skills', {}).get('non_technical', [])
            )
        except:
            candidate_skills = []

        # Generate questions if POST request
        if request.method == 'POST':
            try:
                # Prioritize required skills (from job offer)
                required_skills = offer_skills[:MAX_QUESTIONS]  # Take up to MAX_QUESTIONS required skills
                required_questions = [
                    {"skill": skill, 
                     "question": generate_question(skill),
                     "required": True} 
                    for skill in required_skills
                ]

                # If we have room for more questions, add candidate skills
                remaining_slots = MAX_QUESTIONS - len(required_questions)
                if remaining_slots > 0:
                    # Get candidate skills that aren't in the required skills
                    additional_skills = list(set(candidate_skills) - set(offer_skills))
                    # Take only what we need to reach MAX_QUESTIONS
                    selected_additional_skills = additional_skills[:remaining_slots]
                    additional_questions = [
                        {"skill": skill, 
                         "question": generate_question(skill),
                         "required": False} 
                        for skill in selected_additional_skills
                    ]
                else:
                    additional_questions = []

                # Combine all questions
                all_questions = required_questions + additional_questions
                
                return jsonify({
                    "offer_title": offer['title'],
                    "questions": all_questions
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        # For GET request, render the template
        return render_template(
            'chatbot_interview.html',
            offer=offer,
            skills=list(set(offer_skills + candidate_skills)),
            application=application
        )

    except Exception as e:
        flash(f'Erreur: {str(e)}', 'error')
        return redirect(url_for('candidat_dashboard'))
    finally:
        conn.close()

@app.route('/save_interview_result/<int:offer_id>', methods=['POST'])
@login_required(role='candidat')
def save_interview_result(offer_id):
    if request.method == 'POST':
        data = request.get_json()
        chatbot_score = data.get('score')
        chatbot_feedback = data.get('feedback')

        conn = get_db_connection()
        try:
            conn.execute('''
                UPDATE applications 
                SET chatbot_score = ?, 
                    chatbot_feedback = ?,
                    status = 'completed'
                WHERE user_id = ? AND offer_id = ?
            ''', (chatbot_score, chatbot_feedback, session['user_id'], offer_id))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)})
        finally:
            conn.close()

def update_application_status(user_id, offer_id, score):
    """Update application status based on CV score"""
    conn = get_db_connection()
    try:
        if score >= 5:
            conn.execute('''
                UPDATE applications 
                SET status = 'chatbot-interview' 
                WHERE user_id = ? AND offer_id = ? AND status = 'pending'
            ''', (user_id, offer_id))
        conn.commit()
    except Exception as e:
        print(f"Error updating application status: {e}")
    finally:
        conn.close()

@app.route('/update_application_statuses')
def update_application_statuses():
    """Update application statuses based on scores"""
    conn = get_db_connection()
    try:
        # Get all pending applications with scores >= 5
        conn.execute('''
            UPDATE applications 
            SET status = 'chatbot-interview' 
            WHERE status = 'pending' 
            AND score >= 5
        ''')
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        conn.close()

@app.route("/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json()

    # if it's a list of {question, answer}
    if isinstance(data, list):
        out = []
        for qa in data:
            q = qa.get("question")
            a = qa.get("answer")
            if not q or not a:
                return jsonify({"error": "Missing question or answer"}), 400

            ev = evaluate_answer(q, a)
            # include the original question/answer if you like
            ev["question"] = q
            ev["answer"]   = a
            out.append(ev)

        return jsonify(out)

    # (optional) fall back to single-object support
    question = data.get("question")
    answer   = data.get("answer")
    if not question or not answer:
        return jsonify({"error": "Missing question or answer"}), 400

    result = evaluate_answer(question, answer)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)

