import sqlite3
import json
from difflib import SequenceMatcher
from nltk.corpus import wordnet
import nltk
import logging

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

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    user_id = 2  # Replace with actual user ID
    offer_id = 1  # Replace with actual offer ID
    score = calculate_score(user_id, offer_id)
    print(f"Score for user {user_id} and offer {offer_id}: {score}/10")