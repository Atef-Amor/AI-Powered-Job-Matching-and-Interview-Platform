from flask import Flask, request, jsonify, render_template
from interview_logic import generate_question, evaluate_answer

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")  # This will render the index.html file

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.json
        skills = data.get("skills", [])

        # If no skills are provided, return an error
        if not skills:
            return jsonify({"error": "Skills list cannot be empty."}), 400

        # Generating questions for each skill
        questions = [{"skill": skill, "question": generate_question(skill)} for skill in skills]
        
        # Return the generated questions as a JSON response
        return jsonify(questions)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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


if __name__ == "__main__":
    app.run(debug=True)  # No timeout argument here
