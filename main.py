import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import psycopg2
from psycopg2 import sql, errors

class Database:
    def __init__(self):
        try:
            self.connection = psycopg2.connect(
                dbname="postgres",
                # user="postgres",
                # password="your_password",  # Замените на свой пароль
                host="localhost",
                port="5432"
            )
            self.cursor = self.connection.cursor()
        except psycopg2.OperationalError as e:
            messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к базе данных:\n{str(e)}")
            raise

    def get_data(self, table, columns="*", where=None):
        try:
            query = sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(', ').join(map(sql.Identifier, columns)) if columns != "*" else sql.SQL("*"),
                sql.Identifier(table)
            )
            if where:
                query = sql.SQL("{} WHERE {}").format(query, sql.SQL(where))
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except Exception as e:
            self.connection.rollback()
            raise e

    def get_lookup_data(self, table, display_column):
        try:
            self.cursor.execute(sql.SQL("SELECT id, {} FROM {}").format(
                sql.Identifier(display_column), sql.Identifier(table)))
            return {row[1]: row[0] for row in self.cursor.fetchall()}
        except Exception as e:
            self.connection.rollback()
            raise e

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
        except errors.ForeignKeyViolation:
            self.connection.rollback()
            raise ValueError("Некорректное значение для внешнего ключа")
        except errors.NotNullViolation as e:
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
        except errors.ForeignKeyViolation:
            self.connection.rollback()
            raise ValueError("Некорректное значение для внешнего ключа")
        except errors.NotNullViolation as e:
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
        except errors.ForeignKeyViolation:
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

        # Создаем вкладки
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True)

        self.tabs = {}
        self.trees = {}
        self.buttons = {}

        tables = [
            ("mail_types", "Типы отправлений"),
            ("recipients", "Адресаты"),
            ("employees", "Сотрудники"),
            ("mail_items", "Почтовые отправления"),
            ("parcels", "Вложения")
        ]

        for table, title in tables:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=title)
            self.tabs[table] = tab

            # Создаем Treeview
            tree = ttk.Treeview(tab)
            tree.pack(fill='both', expand=True, side='left', padx=5, pady=5)

            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
            scrollbar.pack(side='right', fill='y')
            tree.configure(yscrollcommand=scrollbar.set)

            self.trees[table] = tree

            # Кнопки управления
            button_frame = ttk.Frame(tab)
            button_frame.pack(fill='x', padx=5, pady=5)

            ttk.Button(button_frame, text="Добавить", command=lambda t=table: self.open_edit_window(t)).pack(side='left', padx=5)
            ttk.Button(button_frame, text="Редактировать", command=lambda t=table: self.open_edit_window(t, True)).pack(side='left', padx=5)
            ttk.Button(button_frame, text="Удалить", command=lambda t=table: self.delete_record(t)).pack(side='left', padx=5)
            ttk.Button(button_frame, text="Обновить", command=lambda t=table: self.load_table_data(t)).pack(side='right', padx=5)

            self.buttons[table] = button_frame

            # Настраиваем колонки
            self.configure_columns(table)

            # Загружаем данные
            self.load_table_data(table)

            # Привязываем событие выбора
            tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def configure_columns(self, table):
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

    def load_table_data(self, table):
        tree = self.trees[table]
        tree.delete(*tree.get_children())

        if table == "mail_items":
            self.db.cursor.execute("""
                SELECT mi.id, mt.type_name, r.full_name, mi.weight, mi.tariff, mi.status
                FROM mail_items mi
                JOIN mail_types mt ON mi.mail_type_id = mt.id
                JOIN recipients r ON mi.recipient_id = r.id
            """)
        elif table == "parcels":
            self.db.cursor.execute("""
                SELECT p.id, mi.id, p.description, p.value
                FROM parcels p
                JOIN mail_items mi ON p.mail_item_id = mi.id
            """)
        else:
            self.db.cursor.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))

        for row in self.db.cursor.fetchall():
            tree.insert("", tk.END, values=row)

    def on_tree_select(self, event):
        tree = event.widget
        if not tree.selection():
            return
        selected_item = tree.selection()[0]
        values = tree.item(selected_item, "values")
        if values:
            self.current_record_id = values[0]
            self.current_table = self.get_current_table()

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
            for field in fields.values():
                if "lookup" in field:
                    lookup_data[field["lookup"]] = self.db.get_lookup_data(field["lookup"], field["display"])

        elif table == "parcels":
            fields = {
                "mail_item_id": {"label": "ID отправления", "type": "combobox", "lookup": "mail_items", "display": "id"},
                "description": {"label": "Описание", "type": "entry"},
                "value": {"label": "Стоимость", "type": "entry"}
            }
            self.db.cursor.execute("SELECT id, id FROM mail_items")
            lookup_data["mail_items"] = {row[1]: row[0] for row in self.db.cursor.fetchall()}

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

        if edit_mode:
            self.db.cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (self.current_record_id,))
            record = self.db.cursor.fetchone()
            colnames = [desc[0] for desc in self.db.cursor.description]
            for i, colname in enumerate(colnames):
                if colname in entries:
                    if isinstance(entries[colname], tuple):
                        combo, lookup_table = entries[colname]
                        if lookup_table:
                            lookup = lookup_data[lookup_table]
                            reverse_lookup = {v: k for k, v in lookup.items()}
                            if record[i] in reverse_lookup:
                                combo.set(reverse_lookup[record[i]])
                        else:
                            combo.set(record[i])
                    else:
                        entries[colname].delete(0, tk.END)
                        entries[colname].insert(0, str(record[i]))

        button_frame = ttk.Frame(window)
        button_frame.pack(fill='x', padx=10, pady=10)

        ttk.Button(button_frame, text="Отмена", command=window.destroy).pack(side='right', padx=5)
        ttk.Button(button_frame, text="Сохранить", command=lambda: self.save_record(table, entries, edit_mode, window)).pack(side='right', padx=5)

    def save_record(self, table, entries, edit_mode, window):
        data = {}
        lookup_data = {}

        for field_name, widget in entries.items():
            try:
                if isinstance(widget, tuple):
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
                else:
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