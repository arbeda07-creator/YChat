print("=" * 35)
print("       welcome to YChat")
print("=" * 35)
while True:
    username = input("Username: ")
    password = input("Password: ")
    if username == "yosuf" and password == "ninjaamk":
      print("login successful")
      break
    else :
      print("wrong username or password")
#=============================
     #القاىْمة الرىْيسيه# 
#=============================    
message = ""

while True:
    print("\n===== YChat Menu =====")
    print("1 - Send Message")
    print("2 - Read Message")
    print("3 - Exit")

    choice = input("choose: ")
    if choice == "1":
        message = input("Write your message: ")

        with open("messages.txt", "a") as file:
            file.write(message + "\n")

        print("Message sent:", message)

     elif choice == "2":
        try:
            with open("messages.txt", "r") as file:
                messages = file.readlines()

            if len(messages) == 0:
                print("No messages yet")
            else:
                print("\n===== Messages =====")
                for msg in messages:
                    print(msg.strip())

        except FileNotFoundError:
            print("No messages yet")

     elif choice == "3":
        print("Goodbye 👋")
        break
     elif choice == "4": 
        with open("messages.txt", "w") as file:
            file.write("")

        print("All messages deleted 🗑️")

     else:
        print("Wrong choice")
    