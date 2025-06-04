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

    def get_lookup_data_reverse(self, table, display_columns):
        try:
            self.cursor.execute(f"SELECT {display_columns}, id FROM {table}")
            return {str(row[0]): row[1] for row in self.cursor.fetchall()}
        except Exception as e:
            messagebox.showerror("Ошибка справочника", f"Ошибка при получении данных из справочника {table}:\n{str(e)}")
            return {}

    def get_mail_items_for_parcels(self):
        """Специальный метод для получения отправлений для вложений"""
        try:
            self.cursor.execute("""
                SELECT mi.id, mi.status, r.full_name 
                FROM mail_items mi
                JOIN recipients r ON mi.recipient_id = r.id
            """)
            return {f"Отправление №{row[0]} [{row[1]}] ({row[2]})": row[0] for row in self.cursor.fetchall()}
        except Exception as e:
            messagebox.showerror("Ошибка справочника", f"Ошибка при получении отправлений:\n{str(e)}")
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
        self.sort_direction = {}

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True)
        
        self.tabs = {}
        self.trees = {}
        self.filters_frame = {}
        
        # Таблицы с русскими названиями
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

    def _create_table_tab(self, table, title):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=title)
        self.tabs[table] = tab
        
        filter_frame = ttk.LabelFrame(tab, text="Фильтры и поиск")
        filter_frame.pack(fill='x', padx=5, pady=5)
        self.filters_frame[table] = filter_frame
        
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame)
        tree.pack(fill='both', expand=True, side='left')
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scrollbar.set)
        self.trees[table] = tree
        
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
        
        self.configure_columns(table)
        tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        self.filters[table] = {}
        self.sort_columns[table] = None
        self.sort_direction[table] = {}
        self.create_filters(table)

    def create_filters(self, table):
        filter_frame = self.filters_frame[table]
        
        ttk.Label(filter_frame, text="Поиск по текстовым полям:").pack(side='left', padx=5)
        search_entry = ttk.Entry(filter_frame, width=30)
        search_entry.pack(side='left', padx=5)
        self.filters[table]["search"] = search_entry
        
        ttk.Button(filter_frame, text="Найти", 
                  command=lambda: self.load_table_data(table)).pack(side='left', padx=5)
        
        if table == "mail_items":
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
        
        elif table == "parcels":
            ttk.Label(filter_frame, text="Стоимость от:").pack(side='left', padx=5)
            value_from = ttk.Entry(filter_frame, width=8)
            value_from.pack(side='left', padx=5)
            self.filters[table]["value_from"] = value_from
            
            ttk.Label(filter_frame, text="до:").pack(side='left', padx=5)
            value_to = ttk.Entry(filter_frame, width=8)
            value_to.pack(side='left', padx=5)
            self.filters[table]["value_to"] = value_to

    def reset_filters(self, table):
        for widget in self.filters[table].values():
            if isinstance(widget, ttk.Entry):
                widget.delete(0, tk.END)
            elif isinstance(widget, tk.StringVar):
                widget.set("все")
        self.sort_columns.pop(table, None)
        self.load_table_data(table)

    def configure_columns(self, table):
        tree = self.trees[table]
        tree["show"] = "headings"
        
        # Словари с русскими названиями столбцов
        russian_headers = {
            "mail_types": {
                "id": "ID",
                "type_name": "Тип отправления",
                "description": "Описание"
            },
            "recipients": {
                "id": "ID",
                "full_name": "ФИО",
                "address": "Адрес",
                "phone": "Телефон",
                "email": "Email"
            },
            "employees": {
                "id": "ID",
                "full_name": "ФИО",
                "position": "Должность",
                "hire_date": "Дата приема"
            },
            "mail_items": {
                "id": "ID",
                "mail_type": "Тип отправления",
                "recipient": "Адресат",
                "weight": "Вес (кг)",
                "tariff": "Тариф",
                "status": "Статус",
                "accepted_date": "Дата приема"
            },
            "parcels": {
                "id": "ID",
                "mail_item": "Отправление",
                "description": "Описание",
                "value": "Стоимость"
            }
        }
        
        if table == "mail_types":
            tree["columns"] = ("id", "type_name", "description")
            for col in tree["columns"]:
                text = russian_headers[table].get(col, col)
                tree.heading(col, text=text, 
                            command=lambda c=col: self.sort_treeview(table, c))
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("type_name", width=150)
            tree.column("description", width=300)
            
        elif table == "recipients":
            tree["columns"] = ("id", "full_name", "address", "phone", "email")
            for col in tree["columns"]:
                text = russian_headers[table].get(col, col)
                tree.heading(col, text=text, 
                            command=lambda c=col: self.sort_treeview(table, c))
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("full_name", width=150)
            tree.column("address", width=200)
            tree.column("phone", width=100)
            tree.column("email", width=150)
            
        elif table == "employees":
            tree["columns"] = ("id", "full_name", "position", "hire_date")
            for col in tree["columns"]:
                text = russian_headers[table].get(col, col)
                tree.heading(col, text=text, 
                            command=lambda c=col: self.sort_treeview(table, c))
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("full_name", width=150)
            tree.column("position", width=150)
            tree.column("hire_date", width=100)
            
        elif table == "mail_items":
            tree["columns"] = ("id", "mail_type", "recipient", "weight", "tariff", "status", "accepted_date")
            for col in tree["columns"]:
                text = russian_headers[table].get(col, col)
                tree.heading(col, text=text, 
                            command=lambda c=col: self.sort_treeview(table, c))
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("mail_type", width=120)
            tree.column("recipient", width=150)
            tree.column("weight", width=70)
            tree.column("tariff", width=70)
            tree.column("status", width=100)
            tree.column("accepted_date", width=100)
            
        elif table == "parcels":
            tree["columns"] = ("id", "mail_item", "description", "value")
            for col in tree["columns"]:
                text = russian_headers[table].get(col, col)
                tree.heading(col, text=text, 
                            command=lambda c=col: self.sort_treeview(table, c))
            tree.column("id", width=50, anchor=tk.CENTER)
            tree.column("mail_item", width=200)
            tree.column("description", width=300)
            tree.column("value", width=100)

    def sort_treeview(self, table, column):
        tree = self.trees[table]
        
        if table not in self.sort_direction:
            self.sort_direction[table] = {}
        
        if column not in self.sort_direction[table]:
            self.sort_direction[table][column] = False
            
        self.sort_direction[table][column] = not self.sort_direction[table][column]
        direction = "DESC" if self.sort_direction[table][column] else "ASC"
        
        self.sort_columns[table] = f"{column} {direction}"
        self.load_table_data(table)
        
        # Обновляем заголовок с учетом направления сортировки
        russian_headers = {
            "mail_types": {"id": "ID", "type_name": "Тип отправления", "description": "Описание"},
            "recipients": {"id": "ID", "full_name": "ФИО", "address": "Адрес", "phone": "Телефон", "email": "Email"},
            "employees": {"id": "ID", "full_name": "ФИО", "position": "Должность", "hire_date": "Дата приема"},
            "mail_items": {"id": "ID", "mail_type": "Тип отправления", "recipient": "Адресат", "weight": "Вес (кг)", 
                          "tariff": "Тариф", "status": "Статус", "accepted_date": "Дата приема"},
            "parcels": {"id": "ID", "mail_item": "Отправление", "description": "Описание", "value": "Стоимость"}
        }
        
        base_text = russian_headers[table].get(column, column)
        tree.heading(column, text=base_text + (" ▼" if direction == "DESC" else " ▲"))

    def load_table_data(self, table):
        tree = self.trees[table]
        tree.delete(*tree.get_children())
        
        where_clauses = []
        params = []
        
        search_text = self.filters[table]["search"].get()
        if search_text:
            if table == "mail_types":
                where_clauses.append("(type_name ILIKE %s OR description ILIKE %s)")
                params.extend([f"%{search_text}%", f"%{search_text}%"])
            elif table == "recipients":
                where_clauses.append("(full_name ILIKE %s OR address ILIKE %s OR email ILIKE %s)")
                params.extend([f"%{search_text}%", f"%{search_text}%", f"%{search_text}%"])
            elif table == "employees":
                where_clauses.append("(full_name ILIKE %s OR position ILIKE %s)")
                params.extend([f"%{search_text}%", f"%{search_text}%"])
            elif table == "mail_items":
                where_clauses.append("(sender_info ILIKE %s OR status ILIKE %s)")
                params.extend([f"%{search_text}%", f"%{search_text}%"])
            elif table == "parcels":
                where_clauses.append("(description ILIKE %s)")
                params.append(f"%{search_text}%")
        
        if table == "mail_items":
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
                SELECT mi.id, mt.type_name, r.full_name, mi.weight, mi.tariff, mi.status,
                       TO_CHAR(mi.accepted_date, 'YYYY-MM-DD')
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
            
            # Форматируем информацию об отправлении
            query = """
                SELECT p.id, 
                       'Отпр. ' || mi.id || ' [' || mi.status || '] (' || r.full_name || ')' as mail_item_info,
                       p.description, p.value
                FROM parcels p
                JOIN mail_items mi ON p.mail_item_id = mi.id
                JOIN recipients r ON mi.recipient_id = r.id
            """
        
        else:
            query = f"SELECT * FROM {table}"
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        if table in self.sort_columns and self.sort_columns[table]:
            query += f" ORDER BY {self.sort_columns[table]}"
        
        try:
            self.db.cursor.execute(query, params)
            for row in self.db.cursor.fetchall():
                tree.insert("", tk.END, values=row)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при загрузке данных из {table}: {str(e)}")

    def on_tree_select(self, event):
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
        current_tab = self.notebook.index(self.notebook.select())
        tables = ["mail_types", "recipients", "employees", "mail_items", "parcels"]
        return tables[current_tab]

    def open_edit_window(self, table, edit_mode=False):
        if edit_mode and not self.current_record_id:
            messagebox.showwarning("Предупреждение", "Выберите запись для редактирования")
            return

        window = tk.Toplevel(self.root)
        window.title("Редактирование" if edit_mode else "Добавление")
        window.geometry("500x600")
        window.grab_set()
        
        fields = {}
        lookup_data = {}
        
        if table == "mail_types":
            fields = {
                "type_name": {"label": "Название типа*", "type": "entry", "required": True},
                "description": {"label": "Описание", "type": "entry", "required": False}
            }
                
        elif table == "recipients":
            fields = {
                "full_name": {"label": "ФИО*", "type": "entry", "required": True},
                "address": {"label": "Адрес*", "type": "entry", "required": True},
                "phone": {"label": "Телефон", "type": "entry", "required": False},
                "email": {"label": "Email*", "type": "entry", "required": True}
            }
                
        elif table == "employees":
            fields = {
                "full_name": {"label": "ФИО*", "type": "entry", "required": True},
                "position": {"label": "Должность", "type": "entry", "required": False},
                "hire_date": {"label": "Дата приема (ГГГГ-ММ-ДД)*", "type": "entry", "required": True}
            }
                
        elif table == "mail_items":
            mail_types = self.db.get_lookup_data_reverse("mail_types", "type_name")
            recipients = self.db.get_lookup_data_reverse("recipients", "full_name")
            employees = self.db.get_lookup_data_reverse("employees", "full_name")
            
            fields = {
                "mail_type_id": {"label": "Тип отправления*", "type": "combobox", "values": list(mail_types.keys()), "required": True},
                "recipient_id": {"label": "Адресат*", "type": "combobox", "values": list(recipients.keys()), "required": True},
                "sender_info": {"label": "Отправитель", "type": "entry", "required": False},
                "weight": {"label": "Вес (кг)*", "type": "entry", "required": True},
                "accepted_by": {"label": "Принявший сотрудник*", "type": "combobox", "values": list(employees.keys()), "required": True},
                "status": {"label": "Статус*", "type": "combobox", "values": ["принято", "в пути", "доставлено"], "required": True}
            }
            
            lookup_data = {
                "mail_type_id": mail_types,
                "recipient_id": recipients,
                "accepted_by": employees
            }
                    
        elif table == "parcels":
            # Используем специальный метод для получения отправлений
            mail_items = self.db.get_mail_items_for_parcels()
            
            fields = {
                "mail_item_id": {"label": "Отправление*", "type": "combobox", "values": list(mail_items.keys()), "required": True},
                "description": {"label": "Описание*", "type": "entry", "required": True},
                "value": {"label": "Стоимость", "type": "entry", "required": False}
            }
            
            lookup_data = {"mail_item_id": mail_items}
        
        entries = {}
        for field_name, field_config in fields.items():
            frame = ttk.Frame(window)
            frame.pack(fill='x', padx=10, pady=5)
            
            label_text = field_config["label"]
            label = ttk.Label(frame, text=label_text, width=30)
            label.pack(side='left', padx=5)
            
            if field_config["type"] == "entry":
                entry = ttk.Entry(frame)
                entry.pack(side='right', fill='x', expand=True, padx=5)
                entries[field_name] = entry
                
            elif field_config["type"] == "combobox":
                combo = ttk.Combobox(frame, values=field_config["values"], state="readonly")
                combo.pack(side='right', fill='x', expand=True, padx=5)
                entries[field_name] = combo
        
        if edit_mode:
            try:
                self.db.cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (self.current_record_id,))
                record = self.db.cursor.fetchone()
                colnames = [desc[0] for desc in self.db.cursor.description]
                
                for i, colname in enumerate(colnames):
                    if colname in entries:
                        value = record[i]
                        if value is None:
                            continue
                            
                        if isinstance(entries[colname], ttk.Combobox):
                            if colname in lookup_data:
                                # Для статуса в отправлениях устанавливаем значение напрямую
                                if table == "mail_items" and colname == "status":
                                    entries[colname].set(value)
                                    continue
                                    
                                # Поиск отображаемого значения по ID
                                for display_value, id_value in lookup_data[colname].items():
                                    if id_value == value:
                                        entries[colname].set(display_value)
                                        break
                            else:
                                entries[colname].set(str(value))
                        else:
                            entries[colname].delete(0, tk.END)
                            entries[colname].insert(0, str(value))
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить данные для редактирования:\n{str(e)}")
                window.destroy()
                return
        
        button_frame = ttk.Frame(window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Отмена", command=window.destroy).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Сохранить", 
                  command=lambda: self.save_record(table, fields, entries, lookup_data, edit_mode, window)).pack(side='right', padx=5)

    def save_record(self, table, fields, entries, lookup_data, edit_mode, window):
        data = {}
        errors = []
        
        for field_name, widget in entries.items():
            try:
                if isinstance(widget, ttk.Combobox):
                    value = widget.get()
                    
                    if fields[field_name]["required"] and not value:
                        errors.append(f"Поле '{fields[field_name]['label']}' обязательно для заполнения")
                        continue
                    
                    # Для статуса в отправлениях сохраняем значение напрямую
                    if table == "mail_items" and field_name == "status":
                        data[field_name] = value
                        continue
                        
                    if field_name in lookup_data:
                        if value in lookup_data[field_name]:
                            data[field_name] = lookup_data[field_name][value]
                        else:
                            errors.append(f"Некорректное значение для '{fields[field_name]['label']}'")
                    else:
                        data[field_name] = value
                    
                else:
                    value = widget.get().strip()
                    
                    if fields[field_name]["required"] and not value:
                        errors.append(f"Поле '{fields[field_name]['label']}' обязательно для заполнения")
                        continue
                    
                    if field_name in ["weight", "tariff", "value"]:
                        if value:
                            try:
                                data[field_name] = float(value)
                            except ValueError:
                                errors.append(f"Некорректное числовое значение для '{fields[field_name]['label']}'")
                        else:
                            data[field_name] = None
                    else:
                        data[field_name] = value
                        
            except Exception as e:
                errors.append(f"Ошибка обработки поля '{fields[field_name]['label']}': {str(e)}")
        
        if errors:
            messagebox.showerror("Ошибки ввода", "\n".join(errors))
            return
        
        if table == "mail_items" and not edit_mode:
            data["accepted_date"] = datetime.now().date()
        
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