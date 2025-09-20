import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from datetime import datetime

"""Bibliotecas clave:

Flask: el microframework web.

sqlite3: para manejar la base de datos local (eco.db).

werkzeug.security: para manejar contraseñas seguras.

datetime: para registrar fechas de creación, etc."""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'eco.db')

app = Flask(__name__)
print("DEBUG: app:", app)
print("DEBUG: type(app):", type(app))
try:
    import flask
    print("DEBUG: flask module file:", flask.__file__)
    import pkgutil
    print("DEBUG: has before_first_request?", hasattr(app, 'before_first_request'))
except Exception as e:
    print("DEBUG: error inspecting flask:", e)
app.secret_key = 'clave-super-secreta-por-favor-cambiar'

"""Establece la ruta a la base de datos
Crea la instancia principal de la app Flask
Define una clave secreta para sesiones (como logins)"""


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
    return db

"""Esta función abre una conexión a la base de datos y la guarda en el contexto global `g` de Flask, para que pueda ser reutilizada en la misma solicitud."""

def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.executescript("""    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        puntos INTEGER DEFAULT 0,
        created_at TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS retos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT,
        dificultad TEXT,
        created_by TEXT,
        created_at TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reto_id INTEGER,
        puntos INTEGER,
        created_at TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        badge TEXT,
        awarded_at TIMESTAMP
    );
    """)
    db.commit()

"""Crea las tablas users, retos, completions, badges si no existen."""

def seed_data():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM retos")
    if cursor.fetchone()['c'] == 0:
        sample = [
            ('Camina o usa la bici durante el día.', 'Media', 'system'),
            ('Evita plásticos de un solo uso por 24 horas.', 'Media', 'system'),
            ('Apaga luces innecesarias en casa.', 'Baja', 'system'),
            ('Siembra una planta o árbol y cuídalo.', 'Alta', 'system'),
            ('Prepara una comida 100% vegetal hoy.', 'Media', 'system')
        ]
        cursor.executemany("INSERT INTO retos (descripcion, dificultad, created_by, created_at) VALUES (?,?,?,?)",
                           [(d, diff, who, datetime.now()) for (d,diff,who) in sample])
        db.commit()

"""Inserta retos iniciales si la tabla retos está vacía."""

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
"""Cierra la conexión a la base de datos al terminar una petición."""

"""@app.before_first_request
def startup():
    try:
        with app.app_context():
            print("🛠 Startup: initialising DB...")
            init_db()
            seed_data()
    except Exception:
        import traceback
        print("Error en startup():")
        traceback.print_exc()
"""

def startup_actions():
    with app.app_context():
        init_db()
        seed_data()

# Ejecutar inmediatamente al importar el módulo (solo una vez)
startup_actions()

"""Ejecuta init_db() y seed_data() apenas se arranca el servidor Flask.
Asegura que la base esté lista antes de que alguien use la app."""



@app.route('/')
def index():
    return render_template('index.html')

"""Muestra el HTML inicial (index.html)"""

@app.route('/registro', methods=['GET','POST'])
def registro():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, created_at) VALUES (?,?,?)",
                           (username, generate_password_hash(password), datetime.now()))
            db.commit()
            flash('Registro exitoso. Inicia sesión.')
            return redirect(url_for('login'))
        except Exception as e:
            flash('El usuario ya existe o hubo un error.')
    return render_template('registro.html')
"""Permite a nuevos usuarios registrarse con nombre y contraseña."""

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('retos'))
        else:
            flash('Credenciales inválidas.')
    return render_template('login.html')
"""Permite a usuarios existentes iniciar sesión."""

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

"""Cierra la sesión del usuario."""

@app.route('/retos')
def retos():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM retos ORDER BY id DESC")
    retos = cursor.fetchall()
    cursor.execute("SELECT puntos FROM users WHERE id = ?", (session['user_id'],))
    puntos = cursor.fetchone()['puntos']
    return render_template('retos.html', retos=retos, puntos=puntos)

"""Muestra la lista de retos disponibles y los puntos actuales del usuario."""

@app.route('/retos/complete', methods=['POST'])
def completar_reto():
    if not session.get('user_id'):
        return jsonify({'success': False, 'error': 'Usuario no autenticado'}), 401
    data = request.get_json()
    reto_id = data.get('reto_id')
    db = get_db()
    cursor = db.cursor()
    # check if already completed today
    cursor.execute("SELECT COUNT(*) as c FROM completions WHERE user_id=? AND reto_id=? AND DATE(created_at)=DATE('now')", (session['user_id'], reto_id))
    if cursor.fetchone()['c'] > 0:
        return jsonify({'success': False, 'error': 'Ya completaste este reto hoy'})
    puntos_ganados = 10
    cursor.execute("INSERT INTO completions (user_id, reto_id, puntos, created_at) VALUES (?,?,?,?)",
                   (session['user_id'], reto_id, puntos_ganados, datetime.now()))
    cursor.execute("UPDATE users SET puntos = puntos + ? WHERE id = ?", (puntos_ganados, session['user_id']))
    db.commit()
    cursor.execute("SELECT puntos FROM users WHERE id = ?", (session['user_id'],))
    puntos_actuales = cursor.fetchone()['puntos']
    # award basic badge
    cursor.execute("SELECT COUNT(*) as c FROM completions WHERE user_id = ?", (session['user_id'],))
    total = cursor.fetchone()['c']
    if total >= 5:
        # check badge exists
        cursor.execute("SELECT COUNT(*) as c FROM badges WHERE user_id=? AND badge=?", (session['user_id'], 'Activista Novato'))
        if cursor.fetchone()['c'] == 0:
            cursor.execute("INSERT INTO badges (user_id, badge, awarded_at) VALUES (?,?,?)",
                           (session['user_id'], 'Activista Novato', datetime.now()))
            db.commit()
    return jsonify({'success': True, 'puntos': puntos_actuales})

"""Marca un reto como completado, otorga puntos y posibles badges."""

@app.route('/eco-calculadora', methods=['GET','POST'])
def eco_calculadora():
    resultado = None
    recomendacion = ''
    if request.method == 'POST':
        try:
            km = float(request.form['km'])
            energia = float(request.form['energia'])
            carne = float(request.form['carne'])
            resultado = round(km * 0.2 + energia * 0.3 + carne * 0.5, 2)
            if resultado < 50:
                recomendacion = 'Tu huella es baja. Mantén prácticas sostenibles.'
            elif resultado < 120:
                recomendacion = 'Huella moderada. Intenta reducir consumo energético y transporte.'
            else:
                recomendacion = 'Huella alta. Considera opciones de transporte y dieta más sostenible.'
        except:
            flash('Por favor ingresa valores numéricos válidos.')
    return render_template('eco_calculadora.html', resultado=resultado, recomendacion=recomendacion)

"""Calcula una estimación de la huella ecológica basada en inputs del usuario."""

@app.route('/submit_reto', methods=['GET','POST'])
def submit_reto():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if request.method=='POST':
        desc = request.form['descripcion'].strip()
        diff = request.form.get('dificultad','Media')
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO retos (descripcion, dificultad, created_by, created_at) VALUES (?,?,?,?)",
                       (desc, diff, session.get('username'), datetime.now()))
        db.commit()
        flash('Reto enviado. ¡Gracias por colaborar!')
        return redirect(url_for('retos'))
    return render_template('submit_reto.html')

"""Permite a usuarios autenticados enviar nuevos retos."""

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT puntos FROM users WHERE id = ?", (session['user_id'],))
    puntos = cursor.fetchone()['puntos']
    cursor.execute("SELECT badge FROM badges WHERE user_id = ?", (session['user_id'],))
    badges = [row['badge'] for row in cursor.fetchall()]
    return render_template('dashboard.html', puntos=puntos, badges=badges)

"""Muestra el dashboard del usuario con puntos y badges obtenidos."""

@app.route('/api/stats')
def api_stats():
    if not session.get('user_id'):
        return jsonify({'labels': [], 'values': []})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT created_at, puntos FROM users WHERE id = ?", (session['user_id'],))
    # For simplicity, create fake progression from completions
    cursor.execute("SELECT DATE(created_at) as day, SUM(puntos) as p FROM completions WHERE user_id=? GROUP BY DATE(created_at) ORDER BY day ASC", (session['user_id'],))
    rows = cursor.fetchall()
    labels = [r['day'] for r in rows]
    values = [r['p'] for r in rows]
    return jsonify({'labels': labels, 'values': values})

"""Provee datos JSON para gráficas de progreso del usuario."""

if __name__ == '__main__':
    app.run(debug=True)

"""Arranca el servidor Flask en modo debug para desarrollo local."""
