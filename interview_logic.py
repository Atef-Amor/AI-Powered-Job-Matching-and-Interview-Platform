from openai_api import call_openai

def generate_question(skill):
    prompt = f"""Generate a technical interview question for testing knowledge of {skill}.
    The question should:
    1. Be specific to {skill}
    2. Test both theoretical knowledge and practical application
    3. Be open-ended enough to evaluate depth of understanding
    Generate only the question, no other text. just one sentence."""
    
    return call_openai(prompt)

def calculate_average_score(scores):
    """
    Calculate the average score from all questions
    Args:
        scores (list): List of dictionaries containing scores and feedback
    Returns:
        float: Average score rounded to 2 decimal places
    """
    if not scores:
        return 0
    
    total = sum(score['score'] for score in scores)
    return round(total / len(scores), 2)

def evaluate_answer(question, answer):
    """Evaluate an interview answer using AI"""
    if not answer.strip():
        return {
            "score": 0,
            "feedback": "No answer provided."
        }

    prompt = f"""You are an expert technical interviewer. Evaluate this interview response:

Question: {question}
Answer: {answer}

Provide:
1. A score from 0-10 (0 = completely wrong, 10 = perfect)
2. Detailed feedback explaining the score

Format your response exactly as:
Score: [single number between 0-10]
Feedback: [Your detailed feedback]"""

    response = call_openai(prompt)
    
    try:
        lines = response.split('\n')
        score_line = next(line for line in lines if line.lower().startswith('score:'))
        score_str = ''.join(filter(str.isdigit, score_line))
        
        # Ensure score is between 0-10
        score = min(10, max(0, int(score_str))) if score_str else 0
        
        feedback_start = response.lower().find('feedback:')
        feedback = response[feedback_start:].replace('Feedback:', '').strip()
        
        return {
            "score": score,
            "feedback": feedback
        }
    except Exception as e:
        return {
            "score": 0,
            "feedback": f"Error parsing response: {str(e)}"
        }