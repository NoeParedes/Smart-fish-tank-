import sqlite3
import argparse
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / 'icc_database.db'

def connect():
    if not DB_PATH.exists():
        print(f'ERROR: No existe la base de datos en {DB_PATH}. Ejecuta primero la aplicación para inicializarla.')
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def show_users():
    conn = connect(); cur = conn.cursor()
    cur.execute('SELECT id_usuario, nombre, correo, tipo_usuario FROM usuarios ORDER BY id_usuario')
    rows = cur.fetchall()
    if not rows:
        print('No hay usuarios.')
    else:
        print('Usuarios:')
        for r in rows:
            print(f"  ID={r['id_usuario']} Nombre={r['nombre']} Correo={r['correo']} Tipo={r['tipo_usuario']}")
    conn.close()

def show_sprinklers():
    conn = connect(); cur = conn.cursor()
    cur.execute('''
        SELECT a.id_aspersor, a.nombre, a.ubicacion, a.estado, a.id_usuario,
               u.nombre AS nombre_usuario
        FROM aspersores a
        LEFT JOIN usuarios u ON a.id_usuario = u.id_usuario
        ORDER BY a.id_usuario, a.id_aspersor
    ''')
    rows = cur.fetchall()
    if not rows:
        print('No hay aspersores.')
    else:
        print('Aspersores:')
        for r in rows:
            owner = r['nombre_usuario'] if r['nombre_usuario'] else 'HUERFANO'
            print(f"  ID={r['id_aspersor']} UsuarioID={r['id_usuario']} Propietario={owner} Nombre={r['nombre']} Ubicacion={r['ubicacion']} Estado={r['estado']}")
    conn.close()

def find_orphans():
    conn = connect(); cur = conn.cursor()
    cur.execute('''
        SELECT a.id_aspersor, a.id_usuario
        FROM aspersores a
        WHERE a.id_usuario NOT IN (SELECT id_usuario FROM usuarios)
        ORDER BY a.id_aspersor
    ''')
    rows = cur.fetchall()
    conn.close()
    return rows

def show_orphans():
    orphans = find_orphans()
    if not orphans:
        print('No hay aspersores huérfanos.')
    else:
        print('Aspersores huérfanos:')
        for r in orphans:
            print(f"  ID={r['id_aspersor']} UsuarioID={r['id_usuario']}")

def delete_orphans():
    orphans = find_orphans()
    if not orphans:
        print('No hay huérfanos que eliminar.')
        return
    conn = connect(); cur = conn.cursor()
    ids = [r['id_aspersor'] for r in orphans]
    cur.executemany('DELETE FROM aspersores WHERE id_aspersor = ?', [(i,) for i in ids])
    conn.commit(); conn.close()
    print(f'Eliminados {len(ids)} aspersores huérfanos: {ids}')

def reassign_orphans(new_user_id: int):
    orphans = find_orphans()
    if not orphans:
        print('No hay huérfanos que reasignar.')
        return
    conn = connect(); cur = conn.cursor()
    # Verificar que el usuario destino exista
    cur.execute('SELECT 1 FROM usuarios WHERE id_usuario = ?', (new_user_id,))
    if not cur.fetchone():
        print(f'ERROR: El usuario destino {new_user_id} no existe.')
        conn.close(); return
    cur.executemany('UPDATE aspersores SET id_usuario = ? WHERE id_aspersor = ?',
                    [(new_user_id, r['id_aspersor']) for r in orphans])
    conn.commit(); conn.close()
    print(f'Reasignados {len(orphans)} aspersores huérfanos al usuario {new_user_id}.')

def main():
    parser = argparse.ArgumentParser(description='Herramientas administración BD (SQLite)')
    sub = parser.add_subparsers(dest='cmd')
    sub.add_parser('show-users')
    sub.add_parser('show-sprinklers')
    sub.add_parser('show-orphans')
    sub.add_parser('delete-orphans')
    r = sub.add_parser('reassign-orphans')
    r.add_argument('--to', type=int, required=True, help='ID usuario destino')

    args = parser.parse_args()
    if args.cmd == 'show-users':
        show_users()
    elif args.cmd == 'show-sprinklers':
        show_sprinklers()
    elif args.cmd == 'show-orphans':
        show_orphans()
    elif args.cmd == 'delete-orphans':
        delete_orphans()
    elif args.cmd == 'reassign-orphans':
        reassign_orphans(args.to)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
