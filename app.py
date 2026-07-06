from datetime import datetime

MESSAGES_FILE = "messages.txt"

print("=" * 35)
print("        welcome to YChat")
print("=" * 35)

while True:
    username = input("Username: ")
    password = input("Password: ")

    if username == "yosuf" and password == "ninjaamk":
        print("login successful")
        break
    else:
        print("wrong username or password")

chat_name = input("Enter your name: ")


def send_message():
    message = input("Write your message: ")
    current_time = datetime.now().strftime("%d/%m/%Y %H:%M")

    with open(MESSAGES_FILE, "a", encoding="utf-8") as file:
        file.write(f"[{chat_name}] - {current_time}\n")
        file.write(message + "\n")
        file.write("-" * 30 + "\n")

    print("Message sent!")


def read_messages():
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as file:
            messages = file.read()

        if messages.strip() == "":
            print("No messages yet")
        else:
            print("\n===== Messages =====")
            print(messages)

    except FileNotFoundError:
        print("No messages yet")


def delete_all_messages():
    confirm = input("Are you sure you want to delete ALL messages? (y/n): ")

    if confirm.lower() == "y":
        with open(MESSAGES_FILE, "w", encoding="utf-8") as file:
            pass
        print("All messages deleted!")
    else:
        print("Delete cancelled.")


def delete_last_message():
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as file:
            content = file.read()

        messages = content.strip().split("-" * 30)

        if len(messages) == 0 or content.strip() == "":
            print("No messages to delete")
            return

        messages = messages[:-1]

        with open(MESSAGES_FILE, "w", encoding="utf-8") as file:
            for msg in messages:
                if msg.strip() != "":
                    file.write(msg.strip() + "\n")
                    file.write("-" * 30 + "\n")

        print("Last message deleted!")

    except FileNotFoundError:
        print("No messages to delete")


def search_messages():
    word = input("Search word: ")

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as file:
            content = file.read()

        if word.lower() in content.lower():
            print("\nFound this word in messages:")
            print(content)
        else:
            print("No matching messages found.")

    except FileNotFoundError:
        print("No messages yet")


while True:
    print("\n===== YChat Menu =====")
    print("1 - Send Message")
    print("2 - Read Messages")
    print("3 - Delete All Messages")
    print("4 - Delete Last Message")
    print("5 - Search Messages")
    print("6 - Exit")

    choice = input("choose: ")

    if choice == "1":
        send_message()

    elif choice == "2":
        read_messages()

    elif choice == "3":
        delete_all_messages()

    elif choice == "4":
        delete_last_message()

    elif choice == "5":
        search_messages()

    elif choice == "6":
        print("Goodbye 👋")
        break

    else:
        print("Wrong choice")