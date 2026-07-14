import os
import datetime
import uuid
import time
from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory, make_response
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# ---------- CONFIGURACIÓN ----------
CHAT_PASSWORD = 'admin123'   # cámbiala si quieres
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- FLASK + SOCKETIO ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave-super-secreta-para-sesiones'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app, cors_allowed_origins="*")

# Historial en RAM y tokens de subida
historial = []
upload_tokens = {}

# ---------- RUTAS ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('texto', '')
        if password == CHAT_PASSWORD:
            session['autenticado'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Contraseña incorrecta')
    return render_template('login.html')

@app.route('/')
def index():
    if not session.get('autenticado'):
        return redirect(url_for('login'))

    token = str(uuid.uuid4())
    upload_tokens[token] = time.time()

    # Limpiar la sesión para forzar re-login al refrescar
    session.clear()

    resp = make_response(render_template('index.html', upload_token=token))
    resp.set_cookie('upload_token', token, max_age=600, httponly=False, samesite='Lax')
    return resp

# ---------- WEBSOCKETS ----------
@socketio.on('connect')
def handle_connect():
    emit('historial', historial)

@socketio.on('mensaje')
def manejar_mensaje(data):
    entrada = {'tipo': 'mensaje', 'datos': data}
    historial.append(entrada)
    emit('mensaje', data, broadcast=True)

# ---------- SUBIDA / DESCARGA ----------
@app.route('/upload', methods=['POST'])
def upload_file():
    token = request.cookies.get('upload_token') or request.form.get('token', '')
    if not token or token not in upload_tokens:
        return 'No autorizado', 401
    if time.time() - upload_tokens[token] > 600:
        del upload_tokens[token]
        return 'Token expirado', 401

    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    original_name = file.filename
    filename = secure_filename(original_name)
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
        filename = f"{base}_{counter}{ext}"
        counter += 1

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    datos_archivo = {
        'nombre': request.form.get('nombre', 'Anónimo'),
        'original': original_name,
        'guardado': filename,
        'url': f'/download/{filename}',
        'size': os.path.getsize(file_path)
    }
    entrada = {'tipo': 'archivo', 'datos': datos_archivo}
    historial.append(entrada)

    socketio.emit('archivo', datos_archivo)
    return '', 204

@app.route('/download/<filename>')
def download_file(filename):
    token = request.cookies.get('upload_token') or request.args.get('token', '')
    if not token or token not in upload_tokens:
        return redirect(url_for('login'))
    filename = secure_filename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    print("🌐 Servidor local en http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)