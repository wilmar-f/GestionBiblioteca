import tkinter as tk
from tkinter import messagebox, filedialog
import os
import networkx as nx
import sqlite3  # Importamos SQLite


# --- Database Manager Class ---
class DatabaseManager:
    def __init__(self, db_name="biblioteca.db"):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            print(f"Error al conectar a la base de datos: {e}")
            # Considera manejar este error en la GUI también

    def _create_tables(self):
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS libros (
                    isbn TEXT PRIMARY KEY UNIQUE,
                    titulo TEXT NOT NULL,
                    autor TEXT NOT NULL,
                    editorial TEXT NOT NULL,
                    disponible INTEGER NOT NULL DEFAULT 1
                )
            ''')
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    dni TEXT PRIMARY KEY UNIQUE,
                    nombre TEXT NOT NULL
                )
            ''')
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS prestamos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    isbn_libro TEXT NOT NULL,
                    dni_usuario TEXT NOT NULL,
                    fecha_prestamo TEXT NOT NULL,
                    activo INTEGER NOT NULL DEFAULT 1, -- 1 si prestado, 0 si devuelto
                    FOREIGN KEY (isbn_libro) REFERENCES libros(isbn) ON DELETE CASCADE,
                    FOREIGN KEY (dni_usuario) REFERENCES usuarios(dni) ON DELETE CASCADE
                )
            ''')
            self.conn.commit()
            print("Tablas verificadas/creadas con éxito.")
        except sqlite3.Error as e:
            print(f"Error al crear tablas: {e}")
            # Considera manejar este error en la GUI

    def close(self):
        if self.conn:
            self.conn.close()

    # --- Métodos para Libros ---
    def add_libro(self, libro):
        try:
            self.cursor.execute(
                "INSERT INTO libros (isbn, titulo, autor, editorial, disponible) VALUES (?, ?, ?, ?, ?)",
                (libro['isbn'], libro['titulo'], libro['autor'], libro['editorial'], 1 if libro['disponible'] else 0)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:  # Si el ISBN ya existe
            return False
        except sqlite3.Error as e:
            print(f"Error al añadir libro: {e}")
            return False

    def get_libro(self, isbn):
        self.cursor.execute("SELECT isbn, titulo, autor, editorial, disponible FROM libros WHERE isbn = ?", (isbn,))
        row = self.cursor.fetchone()
        if row:
            return {
                'isbn': row[0],
                'titulo': row[1],
                'autor': row[2],
                'editorial': row[3],
                'disponible': bool(row[4]),
                'prestado_a': self.get_historial_prestamos_libro(isbn)  # Recuperar historial
            }
        return None

    def delete_libro(self, isbn):
        try:
            # Primero, asegurarse de que no haya préstamos activos para este libro
            self.cursor.execute("SELECT COUNT(*) FROM prestamos WHERE isbn_libro = ? AND activo = 1", (isbn,))
            if self.cursor.fetchone()[0] > 0:
                return False  # No se puede borrar si hay préstamos activos

            self.cursor.execute("DELETE FROM libros WHERE isbn = ?", (isbn,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error al borrar libro: {e}")
            return False

    def get_all_libros(self):
        self.cursor.execute("SELECT isbn, titulo, autor, editorial, disponible FROM libros ORDER BY isbn")
        libros_data = []
        for row in self.cursor.fetchall():
            libro = {
                'isbn': row[0],
                'titulo': row[1],
                'autor': row[2],
                'editorial': row[3],
                'disponible': bool(row[4]),
                'prestado_a': self.get_historial_prestamos_libro(row[0])  # Cargar historial
            }
            libros_data.append(libro)
        return libros_data

    def update_libro_disponibilidad(self, isbn, disponible):
        try:
            self.cursor.execute("UPDATE libros SET disponible = ? WHERE isbn = ?", (1 if disponible else 0, isbn))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error al actualizar disponibilidad: {e}")
            return False

    # --- Métodos para Usuarios ---
    def add_usuario(self, dni, nombre):
        try:
            self.cursor.execute("INSERT INTO usuarios (dni, nombre) VALUES (?, ?)", (dni, nombre))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except sqlite3.Error as e:
            print(f"Error al añadir usuario: {e}")
            return False

    def get_usuario(self, dni):
        self.cursor.execute("SELECT dni, nombre FROM usuarios WHERE dni = ?", (dni,))
        row = self.cursor.fetchone()
        if row:
            return {'dni': row[0], 'nombre': row[1]}
        return None

    def delete_usuario(self, dni):
        try:
            # Primero, asegurarse de que no tenga préstamos activos
            self.cursor.execute("SELECT COUNT(*) FROM prestamos WHERE dni_usuario = ? AND activo = 1", (dni,))
            if self.cursor.fetchone()[0] > 0:
                return False  # No se puede borrar si tiene préstamos activos

            self.cursor.execute("DELETE FROM usuarios WHERE dni = ?", (dni,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error al borrar usuario: {e}")
            return False

    def get_all_usuarios(self):
        self.cursor.execute("SELECT dni, nombre FROM usuarios")
        usuarios_data = {}
        for row in self.cursor.fetchall():
            usuarios_data[row[0]] = row[1]
        return usuarios_data

    # --- Métodos para Préstamos ---
    def registrar_prestamo(self, isbn_libro, dni_usuario):
        try:
            # Marcar el libro como no disponible
            self.update_libro_disponibilidad(isbn_libro, False)
            # Registrar el nuevo préstamo como activo
            self.cursor.execute(
                "INSERT INTO prestamos (isbn_libro, dni_usuario, fecha_prestamo, activo) VALUES (?, ?, datetime('now'), 1)",
                (isbn_libro, dni_usuario)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error al registrar préstamo: {e}")
            # Si falla el préstamo, revertir la disponibilidad si se actualizó
            self.update_libro_disponibilidad(isbn_libro, True)
            return False

    def registrar_devolucion(self, isbn_libro, dni_usuario):
        try:
            # Actualizar el préstamo más reciente de ese libro por ese usuario a inactivo
            self.cursor.execute(
                "UPDATE prestamos SET activo = 0, fecha_devolucion = datetime('now') WHERE isbn_libro = ? AND dni_usuario = ? AND activo = 1 ORDER BY fecha_prestamo DESC LIMIT 1",
                (isbn_libro, dni_usuario)
            )
            if self.cursor.rowcount > 0:
                # Marcar el libro como disponible
                self.update_libro_disponibilidad(isbn_libro, True)
                self.conn.commit()
                return True
            return False  # No se encontró un préstamo activo para ese libro/usuario
        except sqlite3.Error as e:
            print(f"Error al registrar devolución: {e}")
            return False

    def get_historial_prestamos_libro(self, isbn_libro):
        # Obtiene los DNI de los usuarios que han prestado este libro, ordenados por fecha
        self.cursor.execute("SELECT dni_usuario FROM prestamos WHERE isbn_libro = ? ORDER BY fecha_prestamo ASC",
                            (isbn_libro,))
        return [row[0] for row in self.cursor.fetchall()]

    def get_current_borrower(self, isbn_libro):
        # Retorna el DNI del usuario que tiene el libro actualmente prestado (si lo hay)
        self.cursor.execute(
            "SELECT dni_usuario FROM prestamos WHERE isbn_libro = ? AND activo = 1 ORDER BY fecha_prestamo DESC LIMIT 1",
            (isbn_libro,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def get_libros_prestados_by_usuario(self, dni_usuario):
        # Retorna los ISBN de los libros que un usuario tiene actualmente prestados
        self.cursor.execute("SELECT isbn_libro FROM prestamos WHERE dni_usuario = ? AND activo = 1", (dni_usuario,))
        return [row[0] for row in self.cursor.fetchall()]


# --- CLASES DEL MODELO (Lógica de Negocio) - Adaptadas para usar DBManager ---

# La clase BibliotecaISBN ya no necesita mantener la raíz del árbol en memoria
# Su rol ahora es una interfaz que usa el DatabaseManager.
class BibliotecaISBN:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def insertar_libro(self, libro):
        return self.db_manager.add_libro(libro)

    def buscar_libro_por_isbn(self, isbn):
        return self.db_manager.get_libro(isbn)

    def listar_libros_ordenado_por_isbn(self):
        return self.db_manager.get_all_libros()

    def borrar_libro(self, isbn_borrar):
        return self.db_manager.delete_libro(isbn_borrar)


# Ya no se necesita una variable global `usuarios` directamente como diccionario,
# se gestiona a través del db_manager.
# La función _obtener_historial_completo_prestamos también necesita actualizarse.

# --- VARIABLES GLOBALES DEL MODELO ---
db_manager = DatabaseManager()  # Instancia del manejador de la base de datos
biblioteca_isbn = BibliotecaISBN(db_manager)  # Pasa el db_manager a la biblioteca


# La variable global usuarios ahora es una función que carga los usuarios de la BD cuando se necesita
def get_current_users():
    return db_manager.get_all_usuarios()


grafo_biblioteca = nx.DiGraph()  # Sigue siendo en memoria para el grafo


# --- FUNCIONES AUXILIARES DEL MODELO ---
def _obtener_historial_completo_prestamos():
    historial = {}
    libros = biblioteca_isbn.listar_libros_ordenado_por_isbn()
    all_users = get_current_users()  # Obtener usuarios de la BD
    for libro in libros:
        # Aquí, 'prestado_a' viene de la DB (get_historial_prestamos_libro)
        if libro['prestado_a']:
            historial[libro['titulo']] = [all_users.get(dni, "Usuario desconocido") for dni in
                                          reversed(libro['prestado_a'])]
    return historial


# --- INTERFAZ GRÁFICA (Tkinter) ---

class BibliotecaApp:
    def __init__(self, master):
        self.master = master
        master.title("Sistema de Gestión de Biblioteca - Wilmar Eulises Franco Beltran")
        master.geometry("1000x700")

        self.main_frame = tk.Frame(master, padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.status_frame = tk.Frame(self.main_frame, bd=2, relief=tk.GROOVE, padx=5, pady=5)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        self.status_label = tk.Label(self.status_frame, text="Bienvenido al Sistema de Gestión de Biblioteca",
                                     fg="blue")
        self.status_label.pack(fill=tk.X)

        self.current_frame = None
        self.frames = {}

        self.create_main_menu()
        self.create_book_frames()
        self.create_user_frames()
        self.create_loan_frames()
        self.create_export_frame()
        self.create_list_frames()
        self.create_graph_frames()

        # Al iniciar la aplicación, reconstruir el grafo desde la base de datos
        self._reconstruir_grafo_desde_bd()

        # Asegurarse de cerrar la conexión a la BD al cerrar la app
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _on_closing(self):
        db_manager.close()
        self.master.destroy()

    def show_frame(self, frame_name):
        if self.current_frame:
            self.current_frame.pack_forget()
        self.current_frame = self.frames.get(frame_name)
        if self.current_frame:
            self.current_frame.pack(fill=tk.BOTH, expand=True)
            self.set_status("")

    def set_status(self, message, is_error=False):
        self.status_label.config(text=message, fg="red" if is_error else "blue")

    def create_main_menu(self):
        self.menu_frame = tk.Frame(self.main_frame)
        self.menu_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        tk.Label(self.menu_frame, text="Menú Principal", font=("Arial", 14, "bold")).grid(row=0, columnspan=2, pady=10)

        buttons_data = [
            ("Registrar Libro", "registrar_libro_frame"),
            ("Buscar Libro", "buscar_libro_frame"),
            ("Borrar Libro", "borrar_libro_frame"),
            ("Registrar Usuario", "registrar_usuario_frame"),
            ("Buscar Usuario", "buscar_usuario_frame"),
            ("Borrar Usuario", "borrar_usuario_frame"),
            ("Listar Libros", "listar_libros_frame"),
            ("Prestar Libro", "prestar_libro_frame"),
            ("Devolver Libro", "devolver_libro_frame"),
            ("Historial de Préstamos", "historial_prestamos_frame"),
            ("Exportar Información", "exportar_informacion_frame"),
            ("Funciones de Grafo", "grafo_funciones_frame"),
            ("Salir", None)
        ]

        row_idx = 1
        col_idx = 0
        for text, frame_name in buttons_data:
            if frame_name:
                tk.Button(self.menu_frame, text=text, command=lambda fn=frame_name: self.show_frame(fn), width=20,
                          height=2).grid(row=row_idx, column=col_idx, padx=2, pady=5)
            else:
                tk.Button(self.menu_frame, text=text, command=self.master.quit, width=20, height=2).grid(row=row_idx,
                                                                                                         column=col_idx,
                                                                                                         padx=2, pady=5)

            col_idx = 1 - col_idx
            if col_idx == 0:
                row_idx += 1

    def create_book_frames(self):
        # Código para crear los frames de libros (sin cambios significativos aquí, solo las llamadas a las funciones de abajo)
        frame_reg_libro = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["registrar_libro_frame"] = frame_reg_libro
        tk.Label(frame_reg_libro, text="Registrar Nuevo Libro", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_reg_libro, text="ISBN:").pack()
        self.reg_isbn_entry = tk.Entry(frame_reg_libro)
        self.reg_isbn_entry.pack(pady=2)
        tk.Label(frame_reg_libro, text="Título:").pack()
        self.reg_titulo_entry = tk.Entry(frame_reg_libro)
        self.reg_titulo_entry.pack(pady=2)
        tk.Label(frame_reg_libro, text="Autor:").pack()
        self.reg_autor_entry = tk.Entry(frame_reg_libro)
        self.reg_autor_entry.pack(pady=2)
        tk.Label(frame_reg_libro, text="Editorial:").pack()
        self.reg_editorial_entry = tk.Entry(frame_reg_libro)
        self.reg_editorial_entry.pack(pady=2)
        tk.Button(frame_reg_libro, text="Registrar Libro", command=self._registrar_libro_gui).pack(pady=10)

        frame_buscar_libro = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["buscar_libro_frame"] = frame_buscar_libro
        tk.Label(frame_buscar_libro, text="Buscar Libro por ISBN", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_buscar_libro, text="ISBN del Libro:").pack()
        self.buscar_isbn_entry = tk.Entry(frame_buscar_libro)
        self.buscar_isbn_entry.pack(pady=2)
        tk.Button(frame_buscar_libro, text="Buscar", command=self._buscar_libro_gui).pack(pady=10)
        self.libro_encontrado_info = tk.Label(frame_buscar_libro, text="", justify=tk.LEFT)
        self.libro_encontrado_info.pack(pady=5)

        frame_borrar_libro = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["borrar_libro_frame"] = frame_borrar_libro
        tk.Label(frame_borrar_libro, text="Borrar Libro por ISBN", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_borrar_libro, text="ISBN del Libro a Borrar:").pack()
        self.borrar_isbn_entry = tk.Entry(frame_borrar_libro)
        self.borrar_isbn_entry.pack(pady=2)
        tk.Button(frame_borrar_libro, text="Borrar Libro", command=self._borrar_libro_gui).pack(pady=10)

    def create_user_frames(self):
        # Código para crear los frames de usuarios (sin cambios significativos aquí)
        frame_reg_usuario = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["registrar_usuario_frame"] = frame_reg_usuario
        tk.Label(frame_reg_usuario, text="Registrar Nuevo Usuario", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_reg_usuario, text="DNI:").pack()
        self.reg_dni_entry = tk.Entry(frame_reg_usuario)
        self.reg_dni_entry.pack(pady=2)
        tk.Label(frame_reg_usuario, text="Nombre:").pack()
        self.reg_nombre_entry = tk.Entry(frame_reg_usuario)
        self.reg_nombre_entry.pack(pady=2)
        tk.Button(frame_reg_usuario, text="Registrar Usuario", command=self._registrar_usuario_gui).pack(pady=10)

        frame_buscar_usuario = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["buscar_usuario_frame"] = frame_buscar_usuario
        tk.Label(frame_buscar_usuario, text="Buscar Usuario por DNI", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_buscar_usuario, text="DNI del Usuario:").pack()
        self.buscar_dni_entry = tk.Entry(frame_buscar_usuario)
        self.buscar_dni_entry.pack(pady=2)
        tk.Button(frame_buscar_usuario, text="Buscar", command=self._buscar_usuario_gui).pack(pady=10)
        self.usuario_encontrado_info = tk.Label(frame_buscar_usuario, text="")
        self.usuario_encontrado_info.pack(pady=5)

        frame_borrar_usuario = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["borrar_usuario_frame"] = frame_borrar_usuario
        tk.Label(frame_borrar_usuario, text="Borrar Usuario por DNI", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_borrar_usuario, text="DNI del Usuario a Borrar:").pack()
        self.borrar_dni_entry = tk.Entry(frame_borrar_usuario)
        self.borrar_dni_entry.pack(pady=2)
        tk.Button(frame_borrar_usuario, text="Borrar Usuario", command=self._borrar_usuario_gui).pack(pady=10)

    def create_loan_frames(self):
        # Código para crear los frames de préstamos (sin cambios significativos aquí)
        frame_prestar_libro = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["prestar_libro_frame"] = frame_prestar_libro
        tk.Label(frame_prestar_libro, text="Prestar Libro", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_prestar_libro, text="ISBN del Libro:").pack()
        self.prest_isbn_entry = tk.Entry(frame_prestar_libro)
        self.prest_isbn_entry.pack(pady=2)
        tk.Label(frame_prestar_libro, text="DNI del Usuario:").pack()
        self.prest_dni_entry = tk.Entry(frame_prestar_libro)
        self.prest_dni_entry.pack(pady=2)
        tk.Button(frame_prestar_libro, text="Prestar", command=self._prestar_libro_gui).pack(pady=10)

        frame_devolver_libro = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["devolver_libro_frame"] = frame_devolver_libro
        tk.Label(frame_devolver_libro, text="Devolver Libro", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_devolver_libro, text="ISBN del Libro a Devolver:").pack()
        self.dev_isbn_entry = tk.Entry(frame_devolver_libro)
        self.dev_isbn_entry.pack(pady=2)
        tk.Button(frame_devolver_libro, text="Devolver", command=self._devolver_libro_gui).pack(pady=10)

        frame_historial_prestamos = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["historial_prestamos_frame"] = frame_historial_prestamos
        tk.Label(frame_historial_prestamos, text="Historial de Préstamos por Libro", font=("Arial", 12, "bold")).pack(
            pady=10)
        tk.Label(frame_historial_prestamos, text="ISBN del Libro:").pack()
        self.hist_isbn_entry = tk.Entry(frame_historial_prestamos)
        self.hist_isbn_entry.pack(pady=2)
        tk.Button(frame_historial_prestamos, text="Ver Historial", command=self._historial_prestamos_gui).pack(pady=10)
        self.historial_text = tk.Text(frame_historial_prestamos, wrap=tk.WORD, height=10, width=50)
        self.historial_text.pack(pady=5)
        self.historial_text.config(state=tk.DISABLED)

    def create_export_frame(self):
        frame_exportar_info = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["exportar_informacion_frame"] = frame_exportar_info
        tk.Label(frame_exportar_info, text="Exportar Información", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_exportar_info, text="Nombre del archivo:").pack()
        self.export_filename_entry = tk.Entry(frame_exportar_info)
        self.export_filename_entry.pack(pady=2)
        self.export_filename_entry.insert(0, "biblioteca_data.txt")
        tk.Button(frame_exportar_info, text="Seleccionar Ruta y Exportar", command=self._exportar_informacion_gui).pack(
            pady=10)

    def create_list_frames(self):
        frame_listar_libros = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["listar_libros_frame"] = frame_listar_libros
        tk.Label(frame_listar_libros, text="Listado de Libros", font=("Arial", 12, "bold")).pack(pady=10)
        self.list_libros_text = tk.Text(frame_listar_libros, wrap=tk.WORD, height=20, width=70)
        self.list_libros_text.pack(pady=5)
        self.list_libros_text.config(state=tk.DISABLED)
        tk.Button(frame_listar_libros, text="Actualizar Lista", command=self._listar_libros_gui).pack(pady=10)

    def create_graph_frames(self):
        # Código para crear los frames del grafo (sin cambios significativos aquí)
        frame_grafo = tk.Frame(self.main_frame, bd=2, relief=tk.RIDGE)
        self.frames["grafo_funciones_frame"] = frame_grafo
        tk.Label(frame_grafo, text="Funciones de Grafo", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(frame_grafo, text="Buscar usuarios con libros similares (DNI):").pack(pady=5)
        self.grafo_similares_dni_entry = tk.Entry(frame_grafo)
        self.grafo_similares_dni_entry.pack(pady=2)
        tk.Button(frame_grafo, text="Buscar Usuarios Similares", command=self._buscar_usuarios_similares_gui).pack(
            pady=5)
        tk.Label(frame_grafo, text="Recomendar libros para (DNI):").pack(pady=5)
        self.grafo_recomendar_dni_entry = tk.Entry(frame_grafo)
        self.grafo_recomendar_dni_entry.pack(pady=2)
        tk.Button(frame_grafo, text="Recomendar Libros", command=self._recomendar_libros_gui).pack(pady=5)
        tk.Button(frame_grafo, text="Ver Estructura General del Grafo", command=self._ver_estructura_grafo_gui).pack(
            pady=10)
        self.grafo_results_text = tk.Text(frame_grafo, wrap=tk.WORD, height=15, width=70)
        self.grafo_results_text.pack(pady=5)
        self.grafo_results_text.config(state=tk.DISABLED)

    # --- MÉTODOS DE MANEJO DE EVENTOS (GUI) - ADAPTADOS PARA USAR DBManager ---

    def _registrar_libro_gui(self):
        isbn = self.reg_isbn_entry.get().strip()
        titulo = self.reg_titulo_entry.get().strip()
        autor = self.reg_autor_entry.get().strip()
        editorial = self.reg_editorial_entry.get().strip()

        if not all([isbn, titulo, autor, editorial]):
            self.set_status("Todos los campos son obligatorios.", True)
            return

        if not isbn.isdigit():
            self.set_status("El ISBN debe ser numérico.", True)
            return

        libro = {
            'isbn': isbn,
            'titulo': titulo,
            'autor': autor,
            'editorial': editorial,
            'disponible': True,  # Siempre se registra disponible por defecto
            'prestado_a': []  # Esto ya no se usa para registrar, solo para la vista si se carga
        }

        if biblioteca_isbn.insertar_libro(libro):  # Llama a la capa de abstracción de la biblioteca
            self.set_status(f"Libro '{titulo}' con ISBN '{isbn}' registrado con éxito.")
            self.reg_isbn_entry.delete(0, tk.END)
            self.reg_titulo_entry.delete(0, tk.END)
            self.reg_autor_entry.delete(0, tk.END)
            self.reg_editorial_entry.delete(0, tk.END)
            self._actualizar_grafo_libro_creado(libro)
        else:
            self.set_status(f"Advertencia: Ya existe un libro con el ISBN '{isbn}'. No se insertará.", True)

    def _buscar_libro_gui(self):
        isbn_busqueda = self.buscar_isbn_entry.get().strip()

        if not isbn_busqueda:
            self.set_status("Por favor, ingrese el ISBN a buscar.", True)
            self.libro_encontrado_info.config(text="")
            return

        if not isbn_busqueda.isdigit():
            self.set_status("El ISBN debe ser numérico.", True)
            return

        libro_encontrado = biblioteca_isbn.buscar_libro_por_isbn(isbn_busqueda)  # Usa el método de la biblioteca
        if libro_encontrado:
            disponibilidad = "Disponible" if libro_encontrado['disponible'] else "No disponible"

            ultimo_prestamo_dni = db_manager.get_current_borrower(isbn_busqueda)  # Consulta activa en la DB
            ultimo_prestamo = ""
            if ultimo_prestamo_dni:
                nombre_usuario = db_manager.get_usuario(ultimo_prestamo_dni)['nombre']
                ultimo_prestamo = f", Último prestado a: {nombre_usuario} (DNI: {ultimo_prestamo_dni})"

            info_text = (f"ISBN: {libro_encontrado['isbn']}\n"
                         f"Título: {libro_encontrado['titulo']}\n"
                         f"Autor: {libro_encontrado['autor']}\n"
                         f"Editorial: {libro_encontrado['editorial']}\n"
                         f"Estado: {disponibilidad}{ultimo_prestamo}")
            self.libro_encontrado_info.config(text=info_text, justify=tk.LEFT)
            self.set_status("Libro encontrado.")
        else:
            self.set_status("No se encontró ningún libro con ese ISBN.", True)
            self.libro_encontrado_info.config(text="")

    def _borrar_libro_gui(self):
        isbn_borrar = self.borrar_isbn_entry.get().strip()

        if not isbn_borrar:
            self.set_status("Por favor, ingrese el ISBN del libro a borrar.", True)
            return

        if not isbn_borrar.isdigit():
            self.set_status("El ISBN debe ser numérico.", True)
            return

        if messagebox.askyesno("Confirmar Borrado",
                               f"¿Está seguro de que desea borrar el libro con ISBN '{isbn_borrar}'?"):
            # Antes de borrar, verificar si está prestado actualmente
            libro = db_manager.get_libro(isbn_borrar)
            if libro and not libro['disponible']:
                self.set_status(f"No se puede borrar el libro con ISBN '{isbn_borrar}'. Está actualmente prestado.",
                                True)
                return

            if biblioteca_isbn.borrar_libro(isbn_borrar):  # Usa el método de la biblioteca
                self.set_status(f"Libro con ISBN '{isbn_borrar}' borrado con éxito.")
                self.borrar_isbn_entry.delete(0, tk.END)
                self._actualizar_grafo_libro_borrado(isbn_borrar)
            else:
                self.set_status(
                    f"No se encontró ningún libro con el ISBN '{isbn_borrar}' o no se pudo borrar (puede tener préstamos activos).",
                    True)

    def _registrar_usuario_gui(self):
        dni = self.reg_dni_entry.get().strip()
        nombre = self.reg_nombre_entry.get().strip()

        if not all([dni, nombre]):
            self.set_status("DNI y Nombre son obligatorios.", True)
            return

        if not dni.isdigit():
            self.set_status("El DNI debe ser numérico.", True)
            return

        if db_manager.add_usuario(dni, nombre):  # Llama al DatabaseManager
            self.set_status(f"Usuario '{nombre}' registrado con DNI '{dni}' con éxito.")
            self.reg_dni_entry.delete(0, tk.END)
            self.reg_nombre_entry.delete(0, tk.END)
            self._actualizar_grafo_usuario_creado(dni, nombre)
        else:
            self.set_status(f"Ya existe un usuario registrado con el DNI '{dni}'.", True)

    def _buscar_usuario_gui(self):
        dni_busqueda = self.buscar_dni_entry.get().strip()

        if not dni_busqueda:
            self.set_status("Por favor, ingrese el DNI a buscar.", True)
            self.usuario_encontrado_info.config(text="")
            return

        if not dni_busqueda.isdigit():
            self.set_status("El DNI debe ser numérico.", True)
            return

        usuario_encontrado = db_manager.get_usuario(dni_busqueda)  # Llama al DatabaseManager
        if usuario_encontrado:
            self.usuario_encontrado_info.config(
                text=f"Usuario encontrado: DNI: {usuario_encontrado['dni']}, Nombre: {usuario_encontrado['nombre']}")
            self.set_status("Usuario encontrado.")
        else:
            self.set_status("No se encontró ningún usuario con ese DNI.", True)
            self.usuario_encontrado_info.config(text="")

    def _borrar_usuario_gui(self):
        dni_borrar = self.borrar_dni_entry.get().strip()

        if not dni_borrar:
            self.set_status("Por favor, ingrese el DNI del usuario a borrar.", True)
            return

        if not dni_borrar.isdigit():
            self.set_status("El DNI debe ser numérico.", True)
            return

        if messagebox.askyesno("Confirmar Borrado",
                               f"¿Está seguro de que desea borrar el usuario con DNI '{dni_borrar}'?"):
            # Comprobar si el usuario tiene libros prestados ACTIVOS
            libros_prestados_a_usuario = db_manager.get_libros_prestados_by_usuario(dni_borrar)

            if libros_prestados_a_usuario:
                libros_info = [db_manager.get_libro(isbn)['titulo'] for isbn in libros_prestados_a_usuario]
                self.set_status(
                    f"No se puede borrar el usuario. Tiene los siguientes libros prestados: {', '.join(libros_info)}",
                    True)
                return

            if db_manager.delete_usuario(dni_borrar):  # Llama al DatabaseManager
                self.set_status(f"Usuario con DNI '{dni_borrar}' borrado con éxito.")
                self.borrar_dni_entry.delete(0, tk.END)
                self._actualizar_grafo_usuario_borrado(dni_borrar)
            else:
                self.set_status(
                    f"No se encontró ningún usuario con el DNI '{dni_borrar}' o no se pudo borrar (puede tener libros prestados activos).",
                    True)

    def _listar_libros_gui(self):
        libros = biblioteca_isbn.listar_libros_ordenado_por_isbn()  # Usa el método de la biblioteca
        all_users = db_manager.get_all_usuarios()  # Obtener usuarios de la DB

        self.list_libros_text.config(state=tk.NORMAL)
        self.list_libros_text.delete(1.0, tk.END)

        if libros:
            self.list_libros_text.insert(tk.END, "Listado de libros (ordenado por ISBN):\n\n")
            for libro in libros:
                disponibilidad = "Disponible" if libro['disponible'] else "No disponible"

                ultimo_prestamo_dni = db_manager.get_current_borrower(libro['isbn'])
                ultimo_prestamo = "Ninguno"
                if ultimo_prestamo_dni:
                    ultimo_prestamo = all_users.get(ultimo_prestamo_dni,
                                                    "Usuario desconocido") + f" (DNI: {ultimo_prestamo_dni})"

                self.list_libros_text.insert(tk.END, f"ISBN: {libro['isbn']}\n")
                self.list_libros_text.insert(tk.END, f"  Título: {libro['titulo']}\n")
                self.list_libros_text.insert(tk.END, f"  Autor: {libro['autor']}\n")
                self.list_libros_text.insert(tk.END, f"  Editorial: {libro['editorial']}\n")
                self.list_libros_text.insert(tk.END, f"  Estado: {disponibilidad}\n")
                self.list_libros_text.insert(tk.END, f"  Prestado a: {ultimo_prestamo}\n")
                self.list_libros_text.insert(tk.END, "--------------------------------------------------\n")
            self.set_status("Listado de libros actualizado.")
        else:
            self.list_libros_text.insert(tk.END, "No hay libros registrados en la biblioteca.")
            self.set_status("No hay libros registrados.")

        self.list_libros_text.config(state=tk.DISABLED)

    def _prestar_libro_gui(self):
        isbn_prestamo = self.prest_isbn_entry.get().strip()
        dni_usuario = self.prest_dni_entry.get().strip()

        if not all([isbn_prestamo, dni_usuario]):
            self.set_status("ISBN del libro y DNI del usuario son obligatorios.", True)
            return

        if not isbn_prestamo.isdigit():
            self.set_status("El ISBN debe ser numérico.", True)
            return

        if not dni_usuario.isdigit():
            self.set_status("El DNI debe ser numérico.", True)
            return

        libro_encontrado = db_manager.get_libro(isbn_prestamo)  # Obtener de la DB
        if not libro_encontrado:
            self.set_status("No se encontró ningún libro con ese ISBN.", True)
            return

        usuario_encontrado = db_manager.get_usuario(dni_usuario)  # Obtener de la DB
        if not usuario_encontrado:
            self.set_status("El DNI ingresado no corresponde a ningún usuario registrado.", True)
            return

        if not libro_encontrado['disponible']:
            current_borrower_dni = db_manager.get_current_borrower(isbn_prestamo)
            current_borrower_name = db_manager.get_usuario(current_borrower_dni)[
                'nombre'] if current_borrower_dni else "Usuario desconocido"
            self.set_status(f"El libro ya está prestado a {current_borrower_name}.", True)
            return

        if db_manager.registrar_prestamo(isbn_prestamo, dni_usuario):  # Llama al DatabaseManager
            self.set_status(f"Libro '{libro_encontrado['titulo']}' prestado a {usuario_encontrado['nombre']}.")
            self.prest_isbn_entry.delete(0, tk.END)
            self.prest_dni_entry.delete(0, tk.END)
            self._actualizar_grafo_prestamo(dni_usuario, isbn_prestamo)
        else:
            self.set_status("Error al registrar el préstamo.", True)

    def _devolver_libro_gui(self):
        isbn_devolucion = self.dev_isbn_entry.get().strip()

        if not isbn_devolucion:
            self.set_status("Por favor, ingrese el ISBN del libro a devolver.", True)
            return

        if not isbn_devolucion.isdigit():
            self.set_status("El ISBN debe ser numérico.", True)
            return

        libro_encontrado = db_manager.get_libro(isbn_devolucion)  # Obtener de la DB
        if not libro_encontrado:
            self.set_status("No se encontró ningún libro con ese ISBN.", True)
            return

        if libro_encontrado['disponible']:
            self.set_status("El libro no está prestado.", True)
            return

        # Obtener el último prestatario activo
        dni_usuario_devolvio = db_manager.get_current_borrower(isbn_devolucion)
        if not dni_usuario_devolvio:
            self.set_status("Error: No se encontró un préstamo activo para este libro.", True)
            return

        if db_manager.registrar_devolucion(isbn_devolucion, dni_usuario_devolvio):  # Llama al DatabaseManager
            nombre_usuario_devolvio = db_manager.get_usuario(dni_usuario_devolvio)['nombre']
            self.set_status(f"Libro '{libro_encontrado['titulo']}' devuelto por {nombre_usuario_devolvio}.")
            self.dev_isbn_entry.delete(0, tk.END)
            self._actualizar_grafo_devolucion(dni_usuario_devolvio, isbn_devolucion)
        else:
            self.set_status(
                "Error al registrar la devolución. Puede que el libro no esté prestado o no haya un registro activo.",
                True)

    def _historial_prestamos_gui(self):
        isbn_historial = self.hist_isbn_entry.get().strip()

        self.historial_text.config(state=tk.NORMAL)
        self.historial_text.delete(1.0, tk.END)

        if not isbn_historial:
            self.set_status("Por favor, ingrese el ISBN del libro para ver el historial.", True)
            self.historial_text.config(state=tk.DISABLED)
            return

        if not isbn_historial.isdigit():
            self.set_status("El ISBN debe ser numérico.", True)
            self.historial_text.config(state=tk.DISABLED)
            return

        libro_encontrado = db_manager.get_libro(isbn_historial)  # Obtener de la DB
        if libro_encontrado:
            self.historial_text.insert(tk.END, f"Historial de préstamos del libro '{libro_encontrado['titulo']}':\n\n")

            historial_dnis = db_manager.get_historial_prestamos_libro(isbn_historial)  # Obtener de la DB
            all_users = db_manager.get_all_usuarios()  # Obtener usuarios de la DB

            if historial_dnis:
                for i, dni in enumerate(historial_dnis):
                    nombre_usuario = all_users.get(dni, "Usuario desconocido")
                    self.historial_text.insert(tk.END, f"  Préstamo #{i + 1}: DNI: {dni}, Nombre: {nombre_usuario}\n")
            else:
                self.historial_text.insert(tk.END, "  No hay historial de préstamos para este libro.\n")
            self.set_status(f"Historial para '{libro_encontrado['titulo']}' cargado.")
        else:
            self.set_status("No se encontró ningún libro con ese ISBN.", True)
            self.historial_text.insert(tk.END, "No se encontró ningún libro con ese ISBN.")

        self.historial_text.config(state=tk.DISABLED)

    def _exportar_informacion_gui(self):
        nombre_archivo = self.export_filename_entry.get().strip()
        if not nombre_archivo:
            self.set_status("Debe especificar un nombre de archivo para la exportación.", True)
            return

        ruta_guardado = filedialog.askdirectory()
        if not ruta_guardado:
            self.set_status("Exportación cancelada. No se seleccionó ninguna ruta.", True)
            return

        ruta_completa = os.path.join(ruta_guardado, nombre_archivo)

        try:
            with open(ruta_completa, 'w', encoding='utf-8') as archivo:
                archivo.write("--- Información de Libros ---\n")
                libros = biblioteca_isbn.listar_libros_ordenado_por_isbn()  # Usa el método de la biblioteca
                all_users = db_manager.get_all_usuarios()  # Obtener usuarios de la DB

                if libros:
                    for libro in libros:
                        disponibilidad = "Disponible" if libro['disponible'] else "No disponible"
                        ultimo_prestamo_dni = db_manager.get_current_borrower(libro['isbn'])
                        ultimo_prestamo_nombre = all_users.get(ultimo_prestamo_dni,
                                                               'Ninguno') if ultimo_prestamo_dni else 'Ninguno'

                        archivo.write(
                            f"ISBN: {libro['isbn']}, Título: {libro['titulo']}, Autor: {libro['autor']}, Editorial: {libro['editorial']}, Estado: {disponibilidad}, Prestado a: {ultimo_prestamo_nombre} (DNI: {ultimo_prestamo_dni})\n")
                else:
                    archivo.write("No hay libros registrados.\n")

                archivo.write("\n--- Información de Usuarios ---\n")
                usuarios_data = db_manager.get_all_usuarios()  # Obtener usuarios de la DB
                if usuarios_data:
                    for dni, nombre in usuarios_data.items():
                        archivo.write(f"DNI: {dni}, Nombre: {nombre}\n")
                else:
                    archivo.write("No hay usuarios registrados.\n")

                archivo.write("\n--- Historial de Préstamos ---\n")
                # Esto es más complejo, tendrías que iterar sobre la tabla de préstamos en la DB
                db_manager.cursor.execute(
                    "SELECT isbn_libro, dni_usuario, fecha_prestamo, activo FROM prestamos ORDER BY fecha_prestamo DESC")
                prestamos_raw = db_manager.cursor.fetchall()

                if prestamos_raw:
                    for p_isbn, p_dni, p_fecha, p_activo in prestamos_raw:
                        libro_info = db_manager.get_libro(p_isbn)
                        usuario_info = db_manager.get_usuario(p_dni)

                        titulo_libro = libro_info['titulo'] if libro_info else f"ISBN {p_isbn} (desconocido)"
                        nombre_usuario = usuario_info['nombre'] if usuario_info else f"DNI {p_dni} (desconocido)"

                        estado_prestamo = "ACTIVO" if p_activo == 1 else "DEVUELTO"

                        archivo.write(f"Libro: '{titulo_libro}' (ISBN: {p_isbn})\n")
                        archivo.write(f"  Usuario: '{nombre_usuario}' (DNI: {p_dni})\n")
                        archivo.write(f"  Fecha Préstamo: {p_fecha}, Estado: {estado_prestamo}\n")
                        archivo.write("  ---------------------------------------\n")
                else:
                    archivo.write("No hay historial de préstamos registrado.\n")

            self.set_status(f"Información exportada con éxito al archivo '{ruta_completa}'.")
            messagebox.showinfo("Exportación Exitosa", f"Información exportada a:\n{ruta_completa}")

        except Exception as e:
            self.set_status(f"Ocurrió un error al exportar la información: {e}", True)
            messagebox.showerror("Error de Exportación", f"No se pudo exportar la información: {e}")

    # --- Métodos para la gestión y consulta del Grafo (adaptados para usar DBManager) ---

    def _reconstruir_grafo_desde_bd(self):
        """
        Reconstruye el grafo completamente desde los datos de la base de datos.
        Esto se llama al inicio de la aplicación para cargar el estado persistente.
        """
        grafo_biblioteca.clear()  # Limpiar cualquier estado anterior

        # Añadir nodos de usuarios
        all_users = db_manager.get_all_usuarios()
        for dni, nombre in all_users.items():
            grafo_biblioteca.add_node(f"u_{dni}", type='usuario', dni=dni, nombre=nombre)

        # Añadir nodos de libros
        all_libros = db_manager.get_all_libros()
        for libro in all_libros:
            grafo_biblioteca.add_node(f"l_{libro['isbn']}", type='libro', isbn=libro['isbn'], titulo=libro['titulo'],
                                      autor=libro['autor'], editorial=libro['editorial'])

        # Añadir aristas de préstamos activos
        db_manager.cursor.execute("SELECT isbn_libro, dni_usuario FROM prestamos WHERE activo = 1")
        active_loans = db_manager.cursor.fetchall()
        for isbn, dni in active_loans:
            usuario_id = f"u_{dni}"
            libro_id = f"l_{isbn}"
            if grafo_biblioteca.has_node(usuario_id) and grafo_biblioteca.has_node(libro_id):
                grafo_biblioteca.add_edge(usuario_id, libro_id, type='presta')

        self.set_status("Grafo reconstruido desde la base de datos al inicio.")

    def _actualizar_grafo_libro_creado(self, libro):
        """Añade un nodo de libro al grafo."""
        libro_id = f"l_{libro['isbn']}"
        if not grafo_biblioteca.has_node(libro_id):
            grafo_biblioteca.add_node(libro_id, type='libro', isbn=libro['isbn'], titulo=libro['titulo'],
                                      autor=libro['autor'], editorial=libro['editorial'])
            self.set_status(f"Grafo: Libro '{libro['titulo']}' añadido como nodo.", is_error=False)
        else:
            self.set_status(
                f"Grafo: Advertencia - Libro '{libro['titulo']}' (ISBN: {libro['isbn']}) ya existía como nodo.",
                is_error=True)

    def _actualizar_grafo_libro_borrado(self, isbn):
        """Elimina un nodo de libro y sus aristas asociadas del grafo."""
        libro_id = f"l_{isbn}"
        if grafo_biblioteca.has_node(libro_id):
            grafo_biblioteca.remove_node(libro_id)
            self.set_status(f"Grafo: Libro '{isbn}' y sus relaciones eliminados del grafo.", is_error=False)
        else:
            self.set_status(f"Grafo: Advertencia - Libro '{isbn}' no encontrado como nodo para borrar.", is_error=True)

    def _actualizar_grafo_usuario_creado(self, dni, nombre):
        """Añade un nodo de usuario al grafo."""
        usuario_id = f"u_{dni}"
        if not grafo_biblioteca.has_node(usuario_id):
            grafo_biblioteca.add_node(usuario_id, type='usuario', dni=dni, nombre=nombre)
            self.set_status(f"Grafo: Usuario '{nombre}' añadido como nodo.", is_error=False)
        else:
            self.set_status(f"Grafo: Advertencia - Usuario '{nombre}' (DNI: {dni}) ya existía como nodo.",
                            is_error=True)

    def _actualizar_grafo_usuario_borrado(self, dni):
        """Elimina un nodo de usuario y sus aristas asociadas del grafo."""
        usuario_id = f"u_{dni}"
        if grafo_biblioteca.has_node(usuario_id):
            grafo_biblioteca.remove_node(usuario_id)
            self.set_status(f"Grafo: Usuario '{dni}' y sus relaciones eliminados del grafo.", is_error=False)
        else:
            self.set_status(f"Grafo: Advertencia - Usuario '{dni}' no encontrado como nodo para borrar.", is_error=True)

    def _actualizar_grafo_prestamo(self, dni_usuario, isbn_libro):
        """Añade una arista de préstamo en el grafo."""
        usuario_id = f"u_{dni_usuario}"
        libro_id = f"l_{isbn_libro}"

        if not grafo_biblioteca.has_node(usuario_id):
            # En un sistema real, esto no debería pasar si el usuario ya está en la BD.
            # Aquí lo añadimos preventivamente para que el grafo refleje el estado.
            usuario_data = db_manager.get_usuario(dni_usuario)
            if usuario_data:
                grafo_biblioteca.add_node(usuario_id, type='usuario', dni=dni_usuario, nombre=usuario_data['nombre'])
                self.set_status(f"Grafo: Usuario {usuario_data['nombre']} añadido al grafo por préstamo.",
                                is_error=False)
            else:
                self.set_status(f"Grafo: Error - Usuario {dni_usuario} no encontrado en DB al registrar préstamo.",
                                True)
                return

        if not grafo_biblioteca.has_node(libro_id):
            libro_data = db_manager.get_libro(isbn_libro)
            if libro_data:
                grafo_biblioteca.add_node(libro_id, type='libro', isbn=isbn_libro, titulo=libro_data['titulo'],
                                          autor=libro_data['autor'], editorial=libro_data['editorial'])
                self.set_status(f"Grafo: Libro {libro_data['titulo']} añadido al grafo por préstamo.", is_error=False)
            else:
                self.set_status(f"Grafo: Error - Libro {isbn_libro} no encontrado en DB al registrar préstamo.", True)
                return

        grafo_biblioteca.add_edge(usuario_id, libro_id, type='presta')
        self.set_status(
            f"Grafo: Préstamo registrado de '{db_manager.get_usuario(dni_usuario)['nombre']}' a libro '{db_manager.get_libro(isbn_libro)['titulo']}'.",
            False)

    def _actualizar_grafo_devolucion(self, dni_usuario, isbn_libro):
        """Elimina una arista de préstamo del grafo."""
        usuario_id = f"u_{dni_usuario}"
        libro_id = f"l_{isbn_libro}"

        if grafo_biblioteca.has_edge(usuario_id, libro_id):
            grafo_biblioteca.remove_edge(usuario_id, libro_id)
            self.set_status(
                f"Grafo: Préstamo de '{db_manager.get_usuario(dni_usuario)['nombre']}' a libro '{db_manager.get_libro(isbn_libro)['titulo']}' eliminado.",
                False)
        else:
            self.set_status(
                f"Grafo: Advertencia - No se encontró préstamo de '{dni_usuario}' a '{isbn_libro}' en el grafo para eliminar.",
                True)

    def _limpiar_resultados_grafo(self):
        self.grafo_results_text.config(state=tk.NORMAL)
        self.grafo_results_text.delete(1.0, tk.END)
        self.grafo_results_text.config(state=tk.DISABLED)

    def _mostrar_resultados_grafo(self, message):
        self.grafo_results_text.config(state=tk.NORMAL)
        self.grafo_results_text.insert(tk.END, message + "\n\n")
        self.grafo_results_text.config(state=tk.DISABLED)

    def _buscar_usuarios_similares_gui(self):
        self._limpiar_resultados_grafo()
        dni_base = self.grafo_similares_dni_entry.get().strip()
        usuario_base_id = f"u_{dni_base}"

        if not dni_base.isdigit() or usuario_base_id not in grafo_biblioteca:
            self.set_status("DNI no válido o usuario no registrado en el grafo.", True)
            self._mostrar_resultados_grafo("Error: DNI no válido o usuario no registrado en el grafo.")
            return

        usuario_data = db_manager.get_usuario(dni_base)
        usuario_nombre = usuario_data['nombre'] if usuario_data else dni_base

        self.set_status(f"Buscando usuarios similares a {usuario_nombre}...", is_error=False)
        self._mostrar_resultados_grafo(f"Usuarios similares a {usuario_nombre} (DNI: {dni_base}):\n")

        libros_prestados_por_base = set(neighbor for neighbor in grafo_biblioteca.successors(usuario_base_id) if
                                        grafo_biblioteca.nodes[neighbor]['type'] == 'libro')

        if not libros_prestados_por_base:
            self._mostrar_resultados_grafo(f"  El usuario {usuario_nombre} no ha prestado ningún libro aún.")
            self.set_status("El usuario no ha prestado ningún libro.", is_error=True)
            return

        similares_encontrados = {}  # DNI: count_shared_books

        # Iterar solo sobre nodos de tipo 'usuario' en el grafo
        for node_id in grafo_biblioteca.nodes:
            if node_id.startswith('u_') and node_id != usuario_base_id:
                current_dni = node_id.replace('u_', '')
                libros_prestados_por_actual = set(neighbor for neighbor in grafo_biblioteca.successors(node_id) if
                                                  grafo_biblioteca.nodes[neighbor]['type'] == 'libro')

                libros_comunes = libros_prestados_por_base.intersection(libros_prestados_por_actual)

                if len(libros_comunes) > 0:
                    similares_encontrados[current_dni] = len(libros_comunes)

        if similares_encontrados:
            sorted_similares = sorted(similares_encontrados.items(), key=lambda item: item[1], reverse=True)
            for dni, count in sorted_similares:
                nombre_similar = db_manager.get_usuario(dni)['nombre'] if db_manager.get_usuario(
                    dni) else "Usuario desconocido"
                self._mostrar_resultados_grafo(f"  - {nombre_similar} (DNI: {dni}) - {count} libro(s) en común.")
        else:
            self._mostrar_resultados_grafo("  No se encontraron usuarios con libros en común.")
        self.set_status("Búsqueda de usuarios similares completada.")

    def _recomendar_libros_gui(self):
        self._limpiar_resultados_grafo()
        dni_recomendar = self.grafo_recomendar_dni_entry.get().strip()
        usuario_id = f"u_{dni_recomendar}"

        if not dni_recomendar.isdigit() or usuario_id not in grafo_biblioteca:
            self.set_status("DNI no válido o usuario no registrado en el grafo.", True)
            self._mostrar_resultados_grafo("Error: DNI no válido o usuario no registrado en el grafo.")
            return

        usuario_data = db_manager.get_usuario(dni_recomendar)
        usuario_nombre = usuario_data['nombre'] if usuario_data else dni_recomendar

        self.set_status(f"Generando recomendaciones para {usuario_nombre}...", is_error=False)
        self._mostrar_resultados_grafo(f"Libros recomendados para {usuario_nombre} (DNI: {dni_recomendar}):\n")

        libros_ya_prestados = set(neighbor for neighbor in grafo_biblioteca.successors(usuario_id) if
                                  grafo_biblioteca.nodes[neighbor]['type'] == 'libro')

        recomendaciones_candidatas = {}

        similares_encontrados = {}
        for node_id in grafo_biblioteca.nodes:
            if node_id.startswith('u_') and node_id != usuario_id:
                libros_prestados_por_otro = set(neighbor for neighbor in grafo_biblioteca.successors(node_id) if
                                                grafo_biblioteca.nodes[neighbor]['type'] == 'libro')
                if libros_prestados_por_otro.intersection(libros_ya_prestados):
                    similares_encontrados[node_id] = libros_prestados_por_otro

        if similares_encontrados:
            for similar_user_id, libros_otro_usuario in similares_encontrados.items():
                for libro_id in libros_otro_usuario:
                    if libro_id not in libros_ya_prestados:
                        # Asegurarse de que el libro esté disponible para recomendar
                        isbn_libro = libro_id.replace('l_', '')
                        libro_db_info = db_manager.get_libro(isbn_libro)
                        if libro_db_info and libro_db_info['disponible']:
                            recomendaciones_candidatas[libro_id] = recomendaciones_candidatas.get(libro_id, 0) + 1

        if recomendaciones_candidatas:
            sorted_recomendaciones = sorted(recomendaciones_candidatas.items(), key=lambda item: item[1], reverse=True)
            count = 0
            for libro_id, score in sorted_recomendaciones:
                libro_data = grafo_biblioteca.nodes[libro_id]  # Obtener datos del libro del grafo
                self._mostrar_resultados_grafo(
                    f"  - Título: {libro_data['titulo']} (ISBN: {libro_data['isbn']}) - Puntuación: {score}")
                count += 1
                if count >= 5:  # Limitar a 5 recomendaciones
                    break
        else:
            self._mostrar_resultados_grafo(
                "  No se encontraron recomendaciones de libros para este usuario. Pruebe prestando más libros o registrando más usuarios/libros.")
        self.set_status("Recomendaciones de libros completadas.")

    def _ver_estructura_grafo_gui(self):
        self._limpiar_resultados_grafo()
        self.set_status("Mostrando estructura general del grafo...", is_error=False)
        self._mostrar_resultados_grafo("Estructura General del Grafo:\n")

        num_nodes = grafo_biblioteca.number_of_nodes()
        num_edges = grafo_biblioteca.number_of_edges()

        self._mostrar_resultados_grafo(f"  Número total de nodos: {num_nodes}")
        self._mostrar_resultados_grafo(f"  Número total de aristas: {num_edges}\n")

        self._mostrar_resultados_grafo("Nodos (primeros 20 si hay muchos):\n")
        nodes_list = list(grafo_biblioteca.nodes(data=True))
        for i, (node_id, data) in enumerate(nodes_list):
            if i >= 20:
                self._mostrar_resultados_grafo("  ... (más nodos)")
                break
            node_info = f"    - {node_id} (Tipo: {data.get('type', 'desconocido')})"
            if data.get('type') == 'libro':
                node_info += f", Título: {data.get('titulo', 'N/A')}"
            elif data.get('type') == 'usuario':
                node_info += f", Nombre: {data.get('nombre', 'N/A')}"
            self._mostrar_resultados_grafo(node_info)
        self._mostrar_resultados_grafo("\nAristas (primeras 20 si hay muchas):\n")
        edges_list = list(grafo_biblioteca.edges(data=True))
        for i, (u, v, data) in enumerate(edges_list):
            if i >= 20:
                self._mostrar_resultados_grafo("  ... (más aristas)")
                break
            self._mostrar_resultados_grafo(f"    - ({u}) -> ({v}) (Tipo: {data.get('type', 'desconocido')})")

        self._mostrar_resultados_grafo("\nPréstamos Activos Recientes (primeros 10 si hay muchos):\n")

        prestamos_encontrados = 0
        db_manager.cursor.execute(
            "SELECT isbn_libro, dni_usuario, fecha_prestamo FROM prestamos WHERE activo = 1 ORDER BY fecha_prestamo DESC LIMIT 10")
        active_loans_recent = db_manager.cursor.fetchall()

        if active_loans_recent:
            for isbn, dni, fecha_prestamo in active_loans_recent:
                nombre_usuario = db_manager.get_usuario(dni)['nombre'] if db_manager.get_usuario(
                    dni) else "Usuario desconocido"
                libro_info = db_manager.get_libro(isbn)
                titulo_libro = libro_info['titulo'] if libro_info else f"ISBN {isbn} (desconocido)"

                self._mostrar_resultados_grafo(
                    f"  - '{nombre_usuario}' (DNI: {dni}) prestó '{titulo_libro}' (ISBN: {isbn}) el {fecha_prestamo}")
                prestamos_encontrados += 1
            if prestamos_encontrados >= 10:
                self._mostrar_resultados_grafo("  ... (más préstamos activos)")
        else:
            self._mostrar_resultados_grafo("  No hay préstamos activos registrados.")

        self.set_status("Estructura del grafo mostrada.")


# --- INICIO DE LA APLICACIÓN ---
if __name__ == "__main__":
    root = tk.Tk()
    app = BibliotecaApp(root)
    root.mainloop()