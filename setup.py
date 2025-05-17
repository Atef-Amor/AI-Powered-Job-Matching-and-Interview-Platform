import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Table users
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'candidat')),
            nom TEXT,
            prenom TEXT,
            telephone TEXT,
            is_confirmed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Table job_offers
    c.execute('''
        CREATE TABLE IF NOT EXISTS job_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            skills TEXT NOT NULL,
            company_name TEXT NOT NULL,
            location TEXT,
            salary TEXT,
            contract_type TEXT,
            experience INTEGER DEFAULT 0, -- Valeur par défaut pour éviter NULL
            education TEXT DEFAULT 'aucun', -- Valeur par défaut pour éviter NULL
            languages TEXT DEFAULT 'Aucune', -- Valeur par défaut pour éviter NULL
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE CASCADE,
            CHECK (contract_type IN ('CDI', 'CDD', 'Stage', 'Alternance', 'Freelance', NULL))
        )
    ''')

    # Table applications with new columns
    c.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER NOT NULL,
            offer_id INTEGER NOT NULL,
            cv_path TEXT NOT NULL,
            score INTEGER,
            parsed_cv TEXT,
            application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            chatbot_score INTEGER DEFAULT NULL,
            chatbot_feedback TEXT DEFAULT NULL,
            PRIMARY KEY (user_id, offer_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (offer_id) REFERENCES job_offers (id)
        )
    ''')

    # Create default admin if needed
    try:
        admin_email = "atef@gmail.com"
        admin_password = generate_password_hash("atef")
        c.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
                 (admin_email, admin_password, 'admin'))
    except sqlite3.IntegrityError:
        pass

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Base de données initialisée avec succès.")