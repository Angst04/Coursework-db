import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import psycopg2
from psycopg2 import sql

class Database:
    def __init__(self):
        try:
            self.connection = psycopg2.connect(
                dbname="postgres",
                # user="postgres",
                # password="your_password",
                host="localhost",
                port="5432"
            )
            self.cursor = self.connection.cursor()
        except psycopg2.OperationalError as e:
            messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к базе данных:\n{str(e)}")
            raise

    def get_data(self, table, columns="*", where=None, order_by=None):
        query = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(', ').join(map(sql.Identifier, columns)) if columns != "*" else sql.SQL("*"),
            sql.Identifier(table)
        )
        if where:
            query = sql.SQL("{} WHERE {}").format(query, sql.SQL(where))
        if order_by:
            query = sql.SQL("{} ORDER BY {}").format(query, sql.SQL(order_by))
        
        try:
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except Exception as e:
            messagebox.showerror("Ошибка запроса", f"Ошибка при получении данных из таблицы {table}:\n{str(e)}")
            return []

    def get_lookup_data(self, table, display_columns):
        try:
            self.cursor.execute(f"SELECT id, {display_columns} FROM {table}")
            return {row[0]: row[1] for row in self.cursor.fetchall()}
        except Exception as e:
            messagebox.showerror("Ошибка справочника", f"Ошибка при получении данных из справочника {table}:\n{str(e)}")
            return {}

    def insert_data(self, table, data):
        try:
            columns = list(data.keys())
            values = list(data.values())
            query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
                sql.Identifier(table),
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join(sql.Placeholder() * len(columns))
            )
            self.cursor.execute(query, values)
            self.connection.commit()
            return self.cursor.fetchone()[0]
        except psycopg2.errors.ForeignKeyViolation:
            self.connection.rollback()
            raise ValueError("Некорректное значение для внешнего ключа")
        except psycopg2.errors.NotNullViolation as e:
            self.connection.rollback()
            field = str(e).split('column "')[1].split('"')[0]
            raise ValueError(f"Поле '{field}' обязательно для заполнения")
        except Exception as e:
            self.connection.rollback()
            raise ValueError(f"Ошибка при добавлении данных: {str(e)}")

    def update_data(self, table, record_id, data):
        try:
            set_clause = sql.SQL(', ').join(
                sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder(k)) for k in data.keys()
            )
            query = sql.SQL("UPDATE {} SET {} WHERE id = {}").format(
                sql.Identifier(table),
                set_clause,
                sql.Placeholder("record_id")
            )
            self.cursor.execute(query, {**data, "record_id": record_id})
            self.connection.commit()
        except psycopg2.errors.ForeignKeyViolation:
            self.connection.rollback()
            raise ValueError("Некорректное значение для внешнего ключа")
        except psycopg2.errors.NotNullViolation as e:
            self.connection.rollback() 
            field = str(e).split('column "')[1].split('"')[0]
            raise ValueError(f"Поле '{field}' обязательно для заполнения")
        except Exception as e:
            self.connection.rollback()
            raise ValueError(f"Ошибка при обновлении данных: {str(e)}")

    def delete_data(self, table, record_id):
        try:
            query = sql.SQL("DELETE FROM {} WHERE id = {}").format(
                sql.Identifier(table),
                sql.Placeholder()
            )
            self.cursor.execute(query, (record_id,))
            self.connection.commit()
        except psycopg2.errors.ForeignKeyViolation:
            self.connection.rollback()
            raise ValueError("Невозможно удалить запись, так как на нее ссылаются другие таблицы")
        except Exception as e:
            self.connection.rollback()
            raise ValueError(f"Ошибка при удалении данных: {str(e)}")

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Управление почтовыми отправлениями")
        self.root.geometry("1200x800")
        
        try:
            self.db = Database()
        except:
            self.root.destroy()
            return

        self.current_table = None
        self.current_record_id = None
        self.filters = {}
        self.sort_columns = {}

        # Создаем вкладки
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True)
        
        self.tabs = {}
        self.trees = {}
        self.filters_frame = {}
        self.sort_buttons = {}
        
        tables = [
            ("mail_types", "Типы отправлений"),
            ("recipients", "Адресаты"),
            ("employees", "Сотрудники"),
            ("mail_items", "Почтовые отправления"),
            ("parcels", "Вложения")
        ]
        
        for table, title in tables:
            self._create_table_tab(table, title)
            self.load_table_data(table)
            
        # Создаем индексы
        self.create_indexes()

    def _create_table_tab(self, table, title):
        """Создает вкладку для таблицы с фильтрами и сортировкой"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=title)
        self.tabs[table] = tab
        
        # Фрейм для фильтров
        filter_frame = ttk.LabelFrame(tab, text="Фильтры")
        filter_frame.pack(fill='x', padx=5, pady=5)
        self.filters_frame[table] = filter_frame
        
        # Фрейм для дерева
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Дерево
        tree = ttk.Treeview(tree_frame)
        tree.pack(fill='both', expand=True, side='left')
        
        # Скроллбар
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scrollbar.set)
        self.trees[table] = tree
        
        # Кнопки управления
        button_frame = ttk.Frame(tab)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(button_frame, text="Добавить", 
                  command=lambda: self.open_edit_window(table)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Редактировать", 
                  command=lambda: self.open_edit_window(table, True)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Удалить", 
                  command=lambda: self.delete_record(table)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Сбросить фильтры", 
                  command=lambda: self.reset_filters(table)).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Обновить", 
                  command=lambda: self.load_table_data(table)).pack(side='right', padx=5)
        
        # Настраиваем колонки
        self.configure_columns(table)
        
        # Привязываем событие выбора
        tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Инициализируем фильтры
        self.filters[table] = {}
        self.sort_columns[table] = None
        
        # Создаем фильтры
        self.create_filters(table)

    def create_filters(self, table):
        """Создает элементы управления фильтрацией и сортировкой"""
        filter_frame = self.filters_frame[table]
        
        if table == "mail_types":
            ttk.Label(filter_frame, text="Тип отправления:").pack(side='left', padx=5)
            entry = ttk.Entry(filter_frame, width=15)
            entry.pack(side='left', padx=5)
            self.filters[table]["type_name"] = entry
            
            self.sort_buttons[table] = ttk.Button(filter_frame, text="Сортировать по типу", 
                                                  command=lambda: self.toggle_sort(table, "type_name"))
            self.sort_buttons[table].pack(side='left', padx=5)

        elif table == "recipients":
            ttk.Label(filter_frame, text="ФИО:").pack(side='left', padx=5)
            entry = ttk.Entry(filter_frame, width=15)
            entry.pack(side='left', padx=5)
            self.filters[table]["full_name"] = entry
            
            self.sort_buttons[table] = ttk.Button(filter_frame, text="Сортировать по ФИО", 
                                                  command=lambda: self.toggle_sort(table, "full_name"))
            self.sort_buttons[table].pack(side='left', padx=5)

        elif table == "employees":
            ttk.Label(filter_frame, text="ФИО:").pack(side='left', padx=5)
            entry = ttk.Entry(filter_frame, width=15)
            entry.pack(side='left', padx=5)
            self.filters[table]["full_name"] = entry
            
            self.sort_buttons[table] = ttk.Button(filter_frame, text="Сортировать по дате приема", 
                                                  command=lambda: self.toggle_sort(table, "hire_date"))
            self.sort_buttons[table].pack(side='left', padx=5)

        elif table == "mail_items":
            ttk.Label(filter_frame, text="Статус:").pack(side='left', padx=5)
            status_var = tk.StringVar()
            combo = ttk.Combobox(filter_frame, textvariable=status_var, 
                               values=["все", "принято", "в пути", "доставлено"], width=10)
            combo.pack(side='left', padx=5)
            combo.set("все")
            self.filters[table]["status"] = status_var
            
            ttk.Label(filter_frame, text="Вес от:").pack(side='left', padx=5)
            weight_from = ttk.Entry(filter_frame, width=8)
            weight_from.pack(side='left', padx=5)
            self.filters[table]["weight_from"] = weight_from
            
            ttk.Label(filter_frame, text="до:").pack(side='left', padx=5)
            weight_to = ttk.Entry(filter_frame, width=8)
            weight_to.pack(side='left', padx=5)
            self.filters[table]["weight_to"] = weight_to
            
            self.sort_buttons[table] = ttk.Button(filter_frame, text="Сортировать по весу", 
                                                  command=lambda: self.toggle_sort(table, "weight"))
            self.sort_buttons[table].pack(side='left', padx=5)

        elif table == "parcels":
            ttk.Label(filter_frame, text="Стоимость от:").pack(side='left', padx=5)
            value_from = ttk.Entry(filter_frame, width=8)
            value_from.pack(side='left', padx=5)
            self.filters[table]["value_from"] = value_from
            
            ttk.Label(filter_frame, text="до:").pack(side='left', padx=5)
            value_to = ttk.Entry(filter_frame, width=8)
            value_to.pack(side='left', padx=5)
            self.filters[table]["value_to"] = value_to
            
            self.sort_buttons[table] = ttk.Button(filter_frame, text="Сортировать по стоимости", 
                                                  command=lambda: self.toggle_sort(table, "value"))
            self.sort_buttons[table].pack(side='left', padx=5)

    def toggle_sort(self, table, column):
        """Переключает сортировку по столбцу"""
        if self.sort_columns.get(table) == column:
            self.sort_columns[table] = f"{column} DESC"
        else:
            self.sort_columns[table] = column
        self.load_table_data(table)

    def reset_filters(self, table):
        """Сбрасывает фильтры для таблицы"""
        for widget in self.filters[table].values():
            if isinstance(widget, ttk.Entry):
                widget.delete(0, tk.END)
            elif isinstance(widget, tk.StringVar):
                widget.set("все")
        self.sort_columns.pop(table, None)
        self.load_table_data(table)
        if table in self.sort_buttons:
            self.sort_buttons[table].config(text=f"Сортировать по {table.split('_')[-1]}")

    def configure_columns(self, table):
        """Настраивает колонки для Treeview"""
        tree = self.trees[table]
        tree["show"] = "headings"
        
        if table == "mail_types":
            tree["columns"] = ("id", "type_name", "description")
            tree.heading("id", text="ID")
            tree.heading("type_name", text="Тип отправления")
            tree.heading("description", text="Описание")
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("type_name", width=150)
            tree.column("description", width=300)
            
        elif table == "recipients":
            tree["columns"] = ("id", "full_name", "address", "phone", "email")
            tree.heading("id", text="ID")
            tree.heading("full_name", text="ФИО")
            tree.heading("address", text="Адрес")
            tree.heading("phone", text="Телефон")
            tree.heading("email", text="Email")
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("full_name", width=150)
            tree.column("address", width=200)
            tree.column("phone", width=100)
            tree.column("email", width=150)
            
        elif table == "employees":
            tree["columns"] = ("id", "full_name", "position", "hire_date")
            tree.heading("id", text="ID")
            tree.heading("full_name", text="ФИО")
            tree.heading("position", text="Должность")
            tree.heading("hire_date", text="Дата приема")
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("full_name", width=150)
            tree.column("position", width=150)
            tree.column("hire_date", width=100)
            
        elif table == "mail_items":
            tree["columns"] = ("id", "mail_type", "recipient", "weight", "tariff", "status")
            tree.heading("id", text="ID")
            tree.heading("mail_type", text="Тип отправления")
            tree.heading("recipient", text="Адресат")
            tree.heading("weight", text="Вес")
            tree.heading("tariff", text="Тариф")
            tree.heading("status", text="Статус")
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("mail_type", width=120)
            tree.column("recipient", width=150)
            tree.column("weight", width=70)
            tree.column("tariff", width=70)
            tree.column("status", width=100)
            
        elif table == "parcels":
            tree["columns"] = ("id", "mail_item", "description", "value")
            tree.heading("id", text="ID")
            tree.heading("mail_item", text="Отправление")
            tree.heading("description", text="Описание")
            tree.heading("value", text="Стоимость")
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("mail_item", width=100)
            tree.column("description", width=300)
            tree.column("value", width=100)

    def create_indexes(self):
        """Создание индексов для ускорения работы"""
        try:
            # GIN-индекс для full-text поиска в mail_types.description
            self.db.cursor.execute("""
                CREATE EXTENSION IF NOT EXISTS pg_trgm;
                CREATE INDEX IF NOT EXISTS idx_mail_types_gin_description 
                ON mail_types USING gin (description gin_trgm_ops);
            """)
            
            # B-tree составной индекс для точного поиска в recipients
            self.db.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recipients_full_name_address 
                ON recipients (full_name, address);
            """)
            
            # BRIN-индекс для диапазонного поиска в employees
            self.db.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employees_brin_hire_date 
                ON employees USING brin (hire_date);
            """)
            
            # BRIN-индекс для фильтрации по статусу и дате в mail_items
            self.db.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_mail_items_brin_status_date 
                ON mail_items USING brin (accepted_date)
                WHERE status = 'принято';
            """)
            
            # GIN-индекс для поиска в parcels.description
            self.db.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_parcels_gin_description 
                ON parcels USING gin (to_tsvector('russian', description));
            """)
            
            self.db.connection.commit()
        except Exception as e:
            messagebox.showwarning("Индексы", f"Не удалось создать индексы:\n{str(e)}")

    def load_table_data(self, table):
        """Загружает данные из таблицы в Treeview с учетом фильтров и сортировки"""
        tree = self.trees[table]
        tree.delete(*tree.get_children())
        
        where_clauses = []
        params = []
        
        if table == "mail_types":
            if self.filters[table]["type_name"].get():
                where_clauses.append(f"type_name ILIKE %s")
                params.append(f"%{self.filters[table]['type_name'].get()}%")
            query = """
                SELECT id, type_name, description 
                FROM mail_types
            """
            
        elif table == "recipients":
            if self.filters[table]["full_name"].get():
                where_clauses.append(f"full_name ILIKE %s")
                params.append(f"%{self.filters[table]['full_name'].get()}%")
            query = """
                SELECT id, full_name, address, phone, email 
                FROM recipients
            """
            
        elif table == "employees":
            if self.filters[table]["full_name"].get():
                where_clauses.append(f"full_name ILIKE %s")
                params.append(f"%{self.filters[table]['full_name'].get()}%")
            query = """
                SELECT id, full_name, position, hire_date 
                FROM employees
            """
            
        elif table == "mail_items":
            status = self.filters[table]["status"].get()
            weight_from = self.filters[table]["weight_from"].get()
            weight_to = self.filters[table]["weight_to"].get()
            
            if status != "все":
                where_clauses.append("status = %s")
                params.append(status)
            if weight_from:
                where_clauses.append("weight >= %s")
                params.append(weight_from)
            if weight_to:
                where_clauses.append("weight <= %s")
                params.append(weight_to)
            
            query = """
                SELECT mi.id, mt.type_name, r.full_name, mi.weight, mi.tariff, mi.status
                FROM mail_items mi
                JOIN mail_types mt ON mi.mail_type_id = mt.id
                JOIN recipients r ON mi.recipient_id = r.id
            """
            
        elif table == "parcels":
            value_from = self.filters[table]["value_from"].get()
            value_to = self.filters[table]["value_to"].get()
            
            if value_from:
                where_clauses.append("value >= %s")
                params.append(value_from)
            if value_to:
                where_clauses.append("value <= %s")
                params.append(value_to)
            
            query = """
                SELECT p.id, mi.id, p.description, p.value
                FROM parcels p
                JOIN mail_items mi ON p.mail_item_id = mi.id
            """
        
        # Добавляем условия фильтрации
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # Добавляем сортировку
        if table in self.sort_columns and self.sort_columns[table]:
            query += f" ORDER BY {self.sort_columns[table]}"
        
        try:
            self.db.cursor.execute(query, params)
            for row in self.db.cursor.fetchall():
                tree.insert("", tk.END, values=row)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке данных из {table}: {str(e)}")

    def on_tree_select(self, event):
        """Обработчик выбора записи в Treeview"""
        tree = event.widget
        table = self.get_current_table()
        if not tree.selection():
            return
        selected_item = tree.selection()[0]
        values = tree.item(selected_item, "values")
        if values:
            self.current_record_id = values[0]
            self.current_table = table

    def get_current_table(self):
        """Возвращает имя текущей таблицы"""
        current_tab = self.notebook.index(self.notebook.select())
        tables = ["mail_types", "recipients", "employees", "mail_items", "parcels"]
        return tables[current_tab]

    def open_edit_window(self, table, edit_mode=False):
        """Открывает окно редактирования/добавления записи"""
        if edit_mode and not self.current_record_id:
            messagebox.showwarning("Предупреждение", "Выберите запись для редактирования")
            return

        window = tk.Toplevel(self.root)
        window.title("Редактирование" if edit_mode else "Добавление")
        window.geometry("500x600")
        window.grab_set()
        
        # Собираем поля формы
        fields = {}
        lookup_data = {}
        
        if table == "mail_types":
            fields = {
                "type_name": {"label": "Название типа", "type": "entry"},
                "description": {"label": "Описание", "type": "entry"}
            }
                
        elif table == "recipients":
            fields = {
                "full_name": {"label": "ФИО", "type": "entry"},
                "address": {"label": "Адрес", "type": "entry"},
                "phone": {"label": "Телефон", "type": "entry"},
                "email": {"label": "Email", "type": "entry"}
            }
                
        elif table == "employees":
            fields = {
                "full_name": {"label": "ФИО", "type": "entry"},
                "position": {"label": "Должность", "type": "entry"},
                "hire_date": {"label": "Дата приема (ГГГГ-ММ-ДД)", "type": "entry"}
            }
                
        elif table == "mail_items":
            fields = {
                "mail_type_id": {"label": "Тип отправления", "type": "combobox", "lookup": "mail_types", "display": "type_name"},
                "recipient_id": {"label": "Адресат", "type": "combobox", "lookup": "recipients", "display": "full_name"},
                "sender_info": {"label": "Отправитель", "type": "entry"},
                "weight": {"label": "Вес", "type": "entry"},
                "tariff": {"label": "Тариф", "type": "entry"},
                "accepted_date": {"label": "Дата приема (ГГГГ-ММ-ДД)", "type": "entry"},
                "accepted_by": {"label": "Принявший сотрудник", "type": "combobox", "lookup": "employees", "display": "full_name"},
                "status": {"label": "Статус", "type": "combobox", "options": ["принято", "в пути", "доставлено"]}
            }
                
            # Получаем данные для выпадающих списков
            for field in fields.values():
                if "lookup" in field:
                    lookup_data[field["lookup"]] = self.db.get_lookup_data(field["lookup"], field["display"])
                    
        elif table == "parcels":
            fields = {
                "mail_item_id": {"label": "ID отправления", "type": "combobox", "lookup": "mail_items", "display": "id"},
                "description": {"label": "Описание", "type": "entry"},
                "value": {"label": "Стоимость", "type": "entry"}
            }
                
            # Получаем данные для выпадающего списка отправлений
            self.db.cursor.execute("SELECT id, id FROM mail_items")
            lookup_data["mail_items"] = {row[1]: row[0] for row in self.db.cursor.fetchall()}
        
        # Создаем элементы формы
        entries = {}
        for field_name, field_config in fields.items():
            frame = ttk.Frame(window)
            frame.pack(fill='x', padx=10, pady=5)
            
            label = ttk.Label(frame, text=field_config["label"], width=30)
            label.pack(side='left', padx=5)
            
            if field_config["type"] == "entry":
                entry = ttk.Entry(frame)
                entry.pack(side='right', fill='x', expand=True, padx=5)
                entries[field_name] = entry
                
            elif field_config["type"] == "combobox":
                if "options" in field_config:
                    combo = ttk.Combobox(frame, values=field_config["options"], state="readonly")
                else:
                    lookup = lookup_data[field_config["lookup"]]
                    combo = ttk.Combobox(frame, values=list(lookup.keys()), state="readonly")
                combo.pack(side='right', fill='x', expand=True, padx=5)
                entries[field_name] = (combo, field_config.get("lookup"))
        
        # Заполняем форму данными при редактировании
        if edit_mode:
            self.db.cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (self.current_record_id,))
            record = self.db.cursor.fetchone()
            colnames = [desc[0] for desc in self.db.cursor.description]
            
            for i, colname in enumerate(colnames):
                if colname in entries:
                    if isinstance(entries[colname], tuple):  # Combobox
                        combo, lookup_table = entries[colname]
                        if lookup_table:
                            lookup = lookup_data[lookup_table]
                            reverse_lookup = {v: k for k, v in lookup.items()}
                            if record[i] in reverse_lookup:
                                combo.set(reverse_lookup[record[i]])
                        else:
                            combo.set(record[i])
                    else:  # Entry
                        entries[colname].delete(0, tk.END)
                        entries[colname].insert(0, str(record[i]))
        
        # Кнопки сохранения
        button_frame = ttk.Frame(window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Отмена", command=window.destroy).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Сохранить", 
                  command=lambda: self.save_record(table, entries, edit_mode, window)).pack(side='right', padx=5)

    def save_record(self, table, entries, edit_mode, window):
        """Сохраняет запись в базе данных"""
        data = {}
        lookup_data = {}
        
        # Собираем данные из формы
        for field_name, widget in entries.items():
            try:
                if isinstance(widget, tuple):  # Combobox
                    combo, lookup_table = widget
                    value = combo.get()
                    
                    if not value:
                        raise ValueError(f"Поле '{combo.master.children['!label'].cget('text')}' обязательно для заполнения")
                    
                    if lookup_table:
                        if lookup_table not in lookup_data:
                            lookup_data[lookup_table] = self.db.get_lookup_data(lookup_table, "id")
                        
                        if value not in lookup_data[lookup_table]:
                            raise ValueError(f"Некорректное значение для {field_name}")
                        
                        data[field_name] = lookup_data[lookup_table][value]
                    else:
                        data[field_name] = value
                        
                else:  # Entry
                    value = widget.get().strip()
                    label = widget.master.children['!label'].cget('text')
                    
                    if not value:
                        raise ValueError(f"Поле '{label}' обязательно для заполнения")
                    
                    if field_name in ["weight", "tariff", "value"]:
                        float(value)
                    elif field_name in ["hire_date", "accepted_date"]:
                        datetime.strptime(value, "%Y-%m-%d")
                    data[field_name] = value
                    
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e))
                return
        
        try:
            if edit_mode:
                self.db.update_data(table, self.current_record_id, data)
                messagebox.showinfo("Успех", "Данные успешно обновлены")
            else:
                self.db.insert_data(table, data)
                messagebox.showinfo("Успех", "Данные успешно добавлены")
            
            self.load_table_data(table)
            window.destroy()
            
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить данные:\n{str(e)}")

    def delete_record(self, table):
        """Удаляет выбранную запись"""
        if not self.current_record_id:
            messagebox.showwarning("Предупреждение", "Выберите запись для удаления")
            return
            
        if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить эту запись?"):
            try:
                self.db.delete_data(table, self.current_record_id)
                self.load_table_data(table)
                self.current_record_id = None
                messagebox.showinfo("Успех", "Запись успешно удалена")
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e))
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось удалить запись:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()