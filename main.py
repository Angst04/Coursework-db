import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2
from config import DB_CONFIG  # Настройки подключения к БД

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Почтовое отделение")
        self.geometry("1200x800")
        
        # Подключение к БД
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor()
        
        # Создание интерфейса
        self.create_widgets()
        self.load_initial_data()

    def create_widgets(self):
        # Вкладки для разных сущностей
        self.notebook = ttk.Notebook(self)
        
        # Вкладка для почтовых отправлений
        self.mail_frame = ttk.Frame(self.notebook)
        self.create_mail_items_tab(self.mail_frame)
        
        # Добавление других вкладок (адресаты, сотрудники и т.д.)
        self.notebook.add(self.mail_frame, text="Почтовые отправления")
        self.notebook.pack(expand=1, fill="both")

    def create_mail_items_tab(self, parent):
        # Список отправлений
        self.mail_tree = ttk.Treeview(parent, columns=("ID", "Тип", "Адресат", "Статус"), show="headings")
        self.mail_tree.heading("ID", text="ID")
        self.mail_tree.heading("Тип", text="Тип")
        self.mail_tree.heading("Адресат", text="Адресат")
        self.mail_tree.heading("Статус", text="Статус")
        
        # Кнопки управления
        btn_frame = ttk.Frame(parent)
        ttk.Button(btn_frame, text="Добавить", command=self.open_add_mail_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Изменить", command=self.open_edit_mail_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_mail_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Обновить", command=self.load_mail_items).pack(side=tk.LEFT, padx=5)
        
        self.mail_tree.pack(fill=tk.BOTH, expand=1)
        btn_frame.pack(pady=5)

    def load_initial_data(self):
        self.load_mail_items()
        # Загрузка данных для выпадающих списков
        self.load_combobox_data()

    def load_combobox_data(self):
        # Загрузка типов отправлений
        self.cursor.execute("SELECT id, type_name FROM mail_types")
        self.mail_types = {row[1]: row[0] for row in self.cursor.fetchall()}
        
        # Загрузка адресатов
        self.cursor.execute("SELECT id, full_name FROM recipients")
        self.recipients = {row[1]: row[0] for row in self.cursor.fetchall()}

    def load_mail_items(self):
        self.mail_tree.delete(*self.mail_tree.get_children())
        self.cursor.execute("""
            SELECT mi.id, mt.type_name, r.full_name, mi.status 
            FROM mail_items mi
            JOIN mail_types mt ON mi.mail_type_id = mt.id
            JOIN recipients r ON mi.recipient_id = r.id
        """)
        for row in self.cursor.fetchall():
            self.mail_tree.insert("", tk.END, values=row)

    def open_add_mail_dialog(self):
        AddMailDialog(self, "Добавить отправление")

    def open_edit_mail_dialog(self):
        selected = self.mail_tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите отправление для редактирования")
            return
        item_id = self.mail_tree.item(selected[0])['values'][0]
        EditMailDialog(self, "Редактировать отправление", item_id)

    def delete_mail_item(self):
        selected = self.mail_tree.selection()
        if not selected:
            return
        item_id = self.mail_tree.item(selected[0])['values'][0]
        try:
            self.cursor.execute("DELETE FROM mail_items WHERE id = %s", (item_id,))
            self.conn.commit()
            self.load_mail_items()
        except Exception as e:
            self.conn.rollback()
            messagebox.showerror("Ошибка", f"Ошибка удаления: {str(e)}")

class AddMailDialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.geometry("400x300")
        
        self.type_var = tk.StringVar()
        self.recipient_var = tk.StringVar()
        self.weight_var = tk.DoubleVar()
        
        ttk.Label(self, text="Тип отправления:").pack(pady=5)
        self.type_cb = ttk.Combobox(self, textvariable=self.type_var, 
                                  values=list(self.parent.mail_types.keys()))
        self.type_cb.pack(pady=5)
        
        ttk.Label(self, text="Адресат:").pack(pady=5)
        self.recipient_cb = ttk.Combobox(self, textvariable=self.recipient_var,
                                       values=list(self.parent.recipients.keys()))
        self.recipient_cb.pack(pady=5)
        
        ttk.Label(self, text="Вес (г):").pack(pady=5)
        ttk.Entry(self, textvariable=self.weight_var).pack(pady=5)
        
        ttk.Button(self, text="Сохранить", command=self.save).pack(pady=10)
    
    def save(self):
        try:
            mail_type_id = self.parent.mail_types[self.type_var.get()]
            recipient_id = self.parent.recipients[self.recipient_var.get()]
            
            self.parent.cursor.execute("""
                INSERT INTO mail_items (mail_type_id, recipient_id, weight)
                VALUES (%s, %s, %s)
            """, (mail_type_id, recipient_id, self.weight_var.get()))
            
            self.parent.conn.commit()
            self.parent.load_mail_items()
            self.destroy()
        except Exception as e:
            self.parent.conn.rollback()
            messagebox.showerror("Ошибка", f"Ошибка сохранения: {str(e)}")

class EditMailDialog(AddMailDialog):
    def __init__(self, parent, title, item_id):
        super().__init__(parent, title)
        self.item_id = item_id
        self.load_data()
    
    def load_data(self):
        self.parent.cursor.execute("""
            SELECT mt.type_name, r.full_name, mi.weight 
            FROM mail_items mi
            JOIN mail_types mt ON mi.mail_type_id = mt.id
            JOIN recipients r ON mi.recipient_id = r.id
            WHERE mi.id = %s
        """, (self.item_id,))
        data = self.parent.cursor.fetchone()
        
        self.type_var.set(data[0])
        self.recipient_var.set(data[1])
        self.weight_var.set(data[2])
    
    def save(self):
        try:
            mail_type_id = self.parent.mail_types[self.type_var.get()]
            recipient_id = self.parent.recipients[self.recipient_var.get()]
            
            self.parent.cursor.execute("""
                UPDATE mail_items 
                SET mail_type_id = %s,
                    recipient_id = %s,
                    weight = %s
                WHERE id = %s
            """, (mail_type_id, recipient_id, self.weight_var.get(), self.item_id))
            
            self.parent.conn.commit()
            self.parent.load_mail_items()
            self.destroy()
        except Exception as e:
            self.parent.conn.rollback()
            messagebox.showerror("Ошибка", f"Ошибка обновления: {str(e)}")

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()