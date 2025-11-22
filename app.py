from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta, time

app = Flask(__name__)
app.secret_key = 'secret_key'

# Configuración de MySQL
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'ICC'
}

# Función para conectar a la base de datos
def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None


@app.route('/myprofile')
def myprofile():
    nombre_usuario = session['nombre_usuario']
    tipo_usuario = session['tipo_usuario']
    if 'id_usuario' in session:
        id_usuario = session['id_usuario']
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT nombre, correo, tipo_usuario, fecha_creacion
                FROM usuarios 
                WHERE id_usuario = %s
            """, (id_usuario,))
            usuario = cursor.fetchone()
            cursor.close()
            connection.close()
            
            return render_template(
                    'myprofile.html',
                    usuario=usuario,  # Datos del usuario desde la base de datos
                    nombre_usuario=session['nombre_usuario'],  # Desde la sesión
                    tipo_usuario=session['tipo_usuario']       # Desde la sesión
                )
        return "Usuario no encontrado", 404
    return redirect('/login')


@app.route('/update_user_info', methods=['PUT'])
def update_user_info():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        data = request.get_json()
        id_usuario = session['id_usuario']
        nombre = data.get('nombre')
        correo = data.get('correo')


        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            if nombre and correo:
                cursor.execute("""
                    UPDATE usuarios 
                    SET nombre = %s, correo = %s 
                    WHERE id_usuario = %s
                """, (nombre, correo, id_usuario))
            elif nombre:
                cursor.execute("""
                    UPDATE usuarios 
                    SET nombre = %s 
                    WHERE id_usuario = %s
                """, (nombre, id_usuario))
            elif correo:
                cursor.execute("""
                    UPDATE usuarios 
                    SET correo = %s 
                    WHERE id_usuario = %s
                """, (correo, id_usuario))

            connection.commit()
            cursor.close()
            connection.close()

            return jsonify({"message": "Información actualizada exitosamente"}), 200
        except Error as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Acceso no autorizado"}), 401

# Ruta para la página de inicio
@app.route('/')
def index():
    return render_template('index.html')

# Ruta para iniciar sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        connection = get_db_connection()

        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id_usuario, nombre, contrasena, tipo_usuario FROM usuarios WHERE correo = %s", (correo,))
            usuario = cursor.fetchone()
            cursor.close()
            connection.close()

            if usuario and usuario['contrasena'] == contrasena:  # Sin hash
                session['id_usuario'] = usuario['id_usuario']
                session['nombre_usuario'] = usuario['nombre']
                session['tipo_usuario'] = usuario['tipo_usuario']
                return redirect(url_for('dashboard'))
            else:
                flash('Correo o contraseña incorrectos')
    return render_template('login.html')

# Ruta para obtener los datos de los sensores
@app.route('/get_sensor_data', methods=['GET'])
def get_sensor_data():
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT tiempo, humedad1, humedad2, nivel_agua 
            FROM datos_sensores
            ORDER BY tiempo ASC
        """)
        data = cursor.fetchall()
        cursor.close()
        connection.close()

        # Devuelve los datos como JSON
        return jsonify(data)
    return jsonify({"error": "Error al obtener datos"}), 500

@app.route('/get_valve_states', methods=['GET'])
def get_valve_states():
    # Asegúrate de que el usuario esté autenticado
 # Recupera el ID del usuario desde la sesión
    connection = get_db_connection()
    if connection:
        try:
            # Obtener los estados de las primeras dos válvulas (aspersores) del usuario autenticado
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT estado
                FROM aspersores
                WHERE id_usuario = 2
                ORDER BY id_aspersor ASC
                LIMIT 2
            """)
            valves = cursor.fetchall()
            cursor.close()
            connection.close()

            # Verificar si hay suficientes válvulas registradas
            if len(valves) >= 2:
                valve1 = valves[0]['estado'] == 'activo'
                valve2 = valves[1]['estado'] == 'activo'
                # La bomba está activa si al menos una válvula está activa
                pump = valve1 or valve2
                return jsonify({"valve1": valve1, "valve2": valve2, "pump": pump}), 200
            else:
                return jsonify({"error": "No hay suficientes aspersores registrados para este usuario."}), 400

        except Error as e:
            print(f"Error al obtener los estados de las válvulas: {e}")
            return jsonify({"error": "Error al consultar la base de datos."}), 500
    else:
        return jsonify({"error": "No se pudo conectar a la base de datos."}), 500


@app.route('/save_sensor_data', methods=['POST'])
def save_sensor_data():
    if request.method == 'POST':
        data = request.get_json()  # Recibir datos en formato JSON
        id_aspersor = data.get('id_aspersor')  # Identificador del aspersor
        tipo_sensor = data.get('tipo_sensor')  # Tipo de sensor (humedad, temperatura, etc.)
        valor_sensor = data.get('valor_sensor')  # Valor leído por el sensor

        # Verificar que todos los campos están presentes
        if not id_aspersor or not tipo_sensor or valor_sensor is None:
            return jsonify({"error": "Datos incompletos"}), 400

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO datos_sensores (id_aspersor, tipo_sensor, valor_sensor)
                    VALUES (%s, %s, %s)
                """, (id_aspersor, tipo_sensor, valor_sensor))
                connection.commit()
                cursor.close()
                connection.close()
                return jsonify({"message": "Datos guardados exitosamente"}), 201
            except Exception as e:
                print(f"Error al guardar los datos del sensor: {e}")
                return jsonify({"error": "Error al guardar los datos"}), 500
        else:
            return jsonify({"error": "Error al conectar con la base de datos"}), 500

# Ruta para el dashboard (compartido)
@app.route('/dashboard')
def dashboard():
    if 'id_usuario' in session:
        # Si el usuario es administrador, recupera información adicional
        usuarios = []
        if session['tipo_usuario'] == 'admin':
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT id_usuario, nombre, correo, tipo_usuario FROM usuarios WHERE tipo_usuario = 'usuario'")
                usuarios = cursor.fetchall()
                cursor.close()
                connection.close()
        
        # Renderiza el dashboard con usuarios si es admin
        return render_template('dashboard.html', 
                               nombre_usuario=session['nombre_usuario'], 
                               tipo_usuario=session['tipo_usuario'], 
                               usuarios=usuarios)
    else:
        return redirect(url_for('login'))

# Ruta para crear un nuevo usuario
@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'id_usuario' in session and session['tipo_usuario'] == 'admin':
        if request.method == 'POST':
            # Intentar obtener datos desde `request.json` (fetch) o `request.form` (formulario estándar)
            data = request.json if request.is_json else request.form
            nombre = data.get('nombre')
            correo = data.get('correo')
            contrasena = data.get('contrasena')

            if not nombre or not correo or not contrasena:
                flash('Todos los campos son obligatorios.', 'error')
                return redirect(url_for('users'))

            # Conectar a la base de datos y agregar el usuario
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario) VALUES (%s, %s, %s, 'usuario')",
                        (nombre, correo, contrasena)
                    )
                    connection.commit()
                    return jsonify({'message': 'Usuario creado exitosamente.'}), 200
                except Exception as e:
                    return jsonify({'error': f'Error al crear el usuario: {str(e)}'}), 500
                finally:
                    cursor.close()
                    connection.close()

        return render_template(
            'users.html',
            nombre_usuario=session.get('nombre_usuario'),
            tipo_usuario=session.get('tipo_usuario')
        )
    else:
        return redirect(url_for('login'))


# Ruta para el dashboard del usuario
@app.route('/usuario')
def usuario_dashboard():
    if 'id_usuario' in session and session['tipo_usuario'] == 'usuario':
        return render_template('usuario_dashboard.html')
    else:
        return redirect(url_for('login'))

# Ruta para cerrar sesión
@app.route('/dashboard/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))



@app.route('/tables')
def tables():
    return render_template('tables.html')

@app.route('/charts')
def charts():
    return render_template('charts.html')

#SCHEDULE
@app.route('/save_schedule', methods=['POST'])
def save_schedule():
    if 'id_usuario' not in session:
        return jsonify({"error": "Usuario no autenticado"}), 401

    id_aspersor = request.form.get('id_aspersor')
    hora_inicio = request.form.get('hora_inicio')
    duracion_minutos = request.form.get('duracion_minutos')
    frecuencia = request.form.get('frecuencia')

    if not id_aspersor or not hora_inicio or not duracion_minutos or not frecuencia:
        return jsonify({"error": "Datos incompletos"}), 400

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO programaciones_riego (id_aspersor, hora_inicio, duracion_minutos, frecuencia)
                VALUES (%s, %s, %s, %s)
            """, (id_aspersor, hora_inicio, duracion_minutos, frecuencia))
            connection.commit()
            cursor.close()
            connection.close()
            flash("Programación guardada exitosamente.", "success")
            return redirect(url_for('calendar', id_aspersor=id_aspersor))
        except Exception as e:
            print(f"Error al guardar la programación: {e}")
            flash("Error al guardar la programación.", "error")
            return redirect(url_for('schedule_irrigation', id_aspersor=id_aspersor))
    else:
        flash("Error al conectar con la base de datos.", "error")
        return redirect(url_for('schedule_irrigation', id_aspersor=id_aspersor))
    
@app.route('/get_schedules', methods=['GET'])
def get_schedules():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id_programacion, id_aspersor, hora_inicio, duracion_minutos
                FROM programaciones_riego
            """)
            schedules = cursor.fetchall()
            cursor.close()
            connection.close()

            # Convertir campos complejos a tipos básicos
            for schedule in schedules:
                # Convertir `hora_inicio` (DATETIME) a una cadena en formato HH:MM:SS
                if isinstance(schedule['hora_inicio'], datetime):
                    schedule['hora_inicio'] = schedule['hora_inicio'].strftime('%Y-%m-%d %H:%M:%S')

                # Asegurar que `duracion_minutos` sea un entero
                schedule['duracion_minutos'] = int(schedule['duracion_minutos'])

            return jsonify(schedules), 200
        except Exception as e:
            print(f"Error al obtener programaciones: {e}")
            return jsonify({"error": "Error al obtener programaciones."}), 500
    else:
        return jsonify({"error": "Error al conectar a la base de datos."}), 500


@app.route('/users', methods=['GET', 'POST'])
def users():
    if 'id_usuario' not in session or session['tipo_usuario'] != 'admin':
        return redirect(url_for('login'))
    
    connection = get_db_connection()

    # Manejar creación de usuario si la solicitud es POST
    if request.method == 'POST':
        data = request.json
        nombre = data.get('nombre')
        correo = data.get('correo')
        contrasena = data.get('contrasena')

        if not (nombre and correo and contrasena):
            return jsonify({"error": "Todos los campos son obligatorios"}), 400

        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario) VALUES (%s, %s, %s, 'usuario')",
                (nombre, correo, contrasena)
            )
            connection.commit()
            cursor.close()
            return jsonify({"message": "Usuario creado exitosamente"}), 201
        except Exception as e:
            return jsonify({"error": f"Error al crear el usuario: {str(e)}"}), 500

    # Obtener usuarios para mostrar en la plantilla
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id_usuario, nombre, correo FROM usuarios WHERE tipo_usuario = 'usuario'")
    usuarios = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template(
        'users.html',
        usuarios=usuarios,
        nombre_usuario=session['nombre_usuario'],
        tipo_usuario=session['tipo_usuario']
    )



@app.route('/layout-static')
def layout_static():
    return render_template('layout-static.html')

@app.route('/layout-sidenav-light')
def layout_sidenav_light(): 
    return render_template('layout-sidenav-light.html')


@app.route('/404')
def error_404():
    return render_template('404.html')

@app.route('/401')
def error_401():
    return render_template('401.html')

@app.route('/500')
def error_500():
    return render_template('500.html')




@app.route('/calendar/<int:id_aspersor>')
def calendar(id_aspersor):
    nombre_usuario = session['nombre_usuario']
    tipo_usuario = session['tipo_usuario']
    return render_template('calendar.html', id_aspersor=id_aspersor, nombre_usuario=nombre_usuario,tipo_usuario=tipo_usuario)

@app.route('/get_programaciones/<int:id_aspersor>')
def get_programaciones(id_aspersor):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_programacion, hora_inicio, duracion_minutos, fecha_creacion
            FROM programaciones_riego
            WHERE id_aspersor = %s
        """, (id_aspersor,))
        programaciones = cursor.fetchall()
        cursor.close()
        connection.close()

        # Formatear `hora_inicio` (DATETIME) y otros campos si es necesario
        for programacion in programaciones:
            if 'hora_inicio' in programacion and programacion['hora_inicio'] is not None:
                # Convertir `hora_inicio` (DATETIME) a cadena en formato legible
                programacion['hora_inicio'] = programacion['hora_inicio'].strftime('%Y-%m-%d %H:%M:%S')

            if 'fecha_creacion' in programacion and programacion['fecha_creacion'] is not None:
                # Convertir `fecha_creacion` (TIMESTAMP) a cadena
                programacion['fecha_creacion'] = programacion['fecha_creacion'].strftime('%Y-%m-%d %H:%M:%S')

        return jsonify(programaciones), 200
    except Exception as e:
        print(f"Error al obtener programaciones: {e}")
        return jsonify({"error": "Error al obtener programaciones."}), 500

@app.route('/save_irrigation_schedule', methods=['POST'])
def save_irrigation_schedule():
    try:
        data = request.get_json()
        id_aspersor = data.get('id_aspersor')
        hora_inicio = data.get('hora_inicio')  # Formato esperado: 'YYYY-MM-DD HH:MM:SS'
        duracion_minutos = data.get('duracion_minutos')

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO programaciones_riego (id_aspersor, hora_inicio, duracion_minutos)
            VALUES (%s, %s, %s)
        """, (id_aspersor, hora_inicio, duracion_minutos))
        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({"message": "Programación de riego guardada exitosamente!"}), 200
    except Error as e:
        return jsonify({"error": str(e)}), 500



@app.route('/get_aspersor_nombre/<int:id_aspersor>')
def get_aspersor_nombre(id_aspersor):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT nombre FROM aspersores WHERE id_aspersor = %s
        """, (id_aspersor,))
        aspersor = cursor.fetchone()
        cursor.close()
        connection.close()

        if aspersor:
            return jsonify({"nombre": aspersor['nombre']})
        else:
            return jsonify({"error": "Aspersor no encontrado"}), 404
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete_programacion/<int:id_programacion>', methods=['DELETE'])
def delete_programacion(id_programacion):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM programaciones_riego WHERE id_programacion = %s", (id_programacion,))
        connection.commit()
        cursor.close()
        connection.close()
        return jsonify({"success": True})
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/crear_aspersor/<int:id_usuario>', methods=['POST'])
def crear_aspersor(id_usuario):
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    tipo_usuario = session['tipo_usuario']
    usuario_actual = session['id_usuario']

    # Validar permisos
    if tipo_usuario != 'admin' and id_usuario != usuario_actual:
        flash('No tienes permiso para crear aspersores para este usuario.', 'error')
        return redirect(url_for('aspersores'))

    # Obtener datos del formulario
    nombre = request.form.get('nombre')
    ubicacion = request.form.get('ubicacion')

    if not nombre or not ubicacion:
        flash('Todos los campos son obligatorios.', 'error')
        return redirect(url_for('aspersores', id_usuario=id_usuario))

    connection = get_db_connection()
    if not connection:
        flash('Error al conectar con la base de datos.', 'error')
        return redirect(url_for('aspersores'))

    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO aspersores (id_usuario, nombre, ubicacion)
            VALUES (%s, %s, %s)
        """, (id_usuario, nombre, ubicacion))
        connection.commit()
        cursor.close()
        connection.close()

        flash('Aspersor creado exitosamente.', 'success')
        return redirect(url_for('aspersores', id_usuario=id_usuario))
    except Exception as e:
        print(f"Error al crear aspersor: {e}")
        flash('Error al crear el aspersor.', 'error')
        return redirect(url_for('aspersores', id_usuario=id_usuario))


@app.route('/aspersores/', defaults={'id_usuario': None}, methods=['GET'])
@app.route('/aspersores/<int:id_usuario>', methods=['GET'])
def aspersores(id_usuario):
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    tipo_usuario = session['tipo_usuario']
    usuario_actual = session['id_usuario']

    # Verificar permisos
    if id_usuario is None:
        id_usuario = usuario_actual  # Por defecto, muestra los aspersores del usuario actual
    elif tipo_usuario != 'admin' and id_usuario != usuario_actual:
        flash('No tienes permiso para ver estos aspersores.', 'error')
        return redirect(url_for('aspersores'))

    connection = get_db_connection()
    if not connection:
        flash('Error al conectar con la base de datos.', 'error')
        return redirect(url_for('aspersores'))

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_aspersor, nombre, ubicacion, estado
            FROM aspersores
            WHERE id_usuario = %s
        """, (id_usuario,))
        aspersores = cursor.fetchall()
        cursor.close()
        connection.close()

        return render_template('sprinklers.html',
                               aspersores=aspersores,
                               nombre_usuario=session['nombre_usuario'],
                               tipo_usuario=tipo_usuario)
    except Exception as e:
        print(f"Error al obtener aspersores: {e}")
        flash('Error al obtener los aspersores.', 'error')
        return redirect(url_for('aspersores'))

@app.route('/eliminar_aspersor', methods=['POST'])
def eliminar_aspersor():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        id_usuario = session['id_usuario']
        data = request.get_json()  # Obtener datos del cuerpo de la solicitud
        id_aspersor = data.get('id_aspersor')

        if not id_aspersor:
            return jsonify({"error": "Falta el ID del aspersor"}), 400

        connection = get_db_connection()
        if connection:
            try:
                # Eliminar el aspersor
                cursor = connection.cursor()
                cursor.execute("""
                    DELETE FROM aspersores
                    WHERE id_aspersor = %s 
                """, (id_aspersor,))
                connection.commit()
                cursor.close()
                connection.close()

                return jsonify({"message": "Aspersor eliminado correctamente"}), 200
            except mysql.connector.Error as e:
                print(f"Error al eliminar el aspersor: {e}")
                return jsonify({"error": "Error al eliminar el aspersor"}), 500
        else:
            return jsonify({"error": "Error al conectar con la base de datos"}), 500
    else:
        return jsonify({"error": "Acceso no autorizado"}), 401


@app.route('/actualizar_aspersor', methods=['POST'])
def actualizar_aspersor():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        nombre_usuario = session['nombre_usuario']
        tipo_usuario = session['tipo_usuario']
        id_usuario = session['id_usuario']

        if request.content_type == 'application/json':
            data = request.get_json()
        else:
            data = request.form

        # Obtener los datos enviados por el cliente
        id_aspersor = data.get('id_aspersor')
        nombre = data.get('nombre')
        ubicacion = data.get('ubicacion')

        # Validar que los datos necesarios estén presentes
        if not id_aspersor or not nombre or not ubicacion:
            flash('Datos incompletos. Asegúrate de que todos los campos están llenos.', 'error')
            return redirect(url_for('aspersores'))

        # Conexión a la base de datos para actualizar el aspersor
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    UPDATE aspersores 
                    SET nombre = %s, ubicacion = %s
                    WHERE id_aspersor = %s 
                """, (nombre, ubicacion, id_aspersor))
                connection.commit()
                cursor.close()
            except Error as e:
                print(f"Error al actualizar el aspersor: {e}")
                return jsonify({"message": "Error al actualizar el aspersor. Por favor, inténtalo de nuevo.", "status": "error"}), 500
            finally:
                connection.close()

        # Después de actualizar, recuperar la lista de aspersores actualizada
        connection = get_db_connection()
        aspersores = []
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id_aspersor, nombre, ubicacion, estado
                FROM aspersores
                WHERE id_usuario = %s
            """, (id_usuario,))
            aspersores = cursor.fetchall()
            cursor.close()
            connection.close()

        # Redirigir a la página de aspersores con los datos actualizados
        return jsonify({"message": "Aspersor actualizado exitosamente.", "status": "success"}), 200

    else:
        # Si el usuario no está autenticado, redirigir al inicio de sesión
        flash('Por favor, inicia sesión para continuar.', 'error')
        return redirect(url_for('login'))

@app.route('/actualizar_estado_aspersor', methods=['POST'])
def actualizar_estado_aspersor():
    if 'id_usuario' in session:  # Asegurarse de que el usuario está logueado
        data = request.get_json()
        aspersor_id = data.get('id_aspersor')
        nuevo_estado = data.get('estado')

        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            print((nuevo_estado,aspersor_id))
            cursor.execute("UPDATE aspersores SET estado = %s WHERE id_aspersor = %s", (nuevo_estado, aspersor_id))
            connection.commit()
            cursor.close()
            connection.close()

        return jsonify({"message": "Estado actualizado exitosamente"}), 200

    return jsonify({"error": "Acceso no autorizado"}), 401


@app.route('/eliminar_usuario', methods=['POST'])
def eliminar_usuario():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        id_usuario = session['id_usuario']
        data = request.get_json()  # Obtener datos del cuerpo de la solicitud
        id_usuario_a_eliminar = data.get('id_usuario')

        if not id_usuario_a_eliminar:
            return jsonify({"error": "Falta el ID del usuario"}), 400

        connection = get_db_connection()
        if connection:
            try:
                # Eliminar el usuario
                cursor = connection.cursor()
                cursor.execute("""
                    DELETE FROM usuarios
                    WHERE id_usuario = %s
                """, (id_usuario_a_eliminar,))
                connection.commit()
                cursor.close()
                connection.close()

                return jsonify({"message": "Usuario eliminado correctamente"}), 200
            except mysql.connector.Error as e:
                print(f"Error al eliminar el usuario: {e}")
                return jsonify({"error": "Error al eliminar el usuario"}), 500
        else:
            return jsonify({"error": "Error al conectar con la base de datos"}), 500
    else:
        return jsonify({"error": "Acceso no autorizado"}), 401


@app.route('/cambiar_modo', methods=['POST'])
def cambiar_modo():
    data = request.get_json()
    modo = data.get('modo')

    if modo not in ['automatico', 'manual']:
        return jsonify({"error": "Modo no válido"}), 400

    # Aquí puedes agregar la lógica para manejar el modo automático/manual
    # Por ejemplo, guardar el estado en la base de datos o en la sesión

    return jsonify({"message": f"Modo cambiado a {modo}"}), 200

if __name__ == '__main__':
    app.run(debug=True)
