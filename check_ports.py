import serial.tools.list_ports

def list_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No se encontraron puertos COM disponibles.")
        print("Asegúrate de que el Arduino esté conectado por USB.")
    else:
        print("Puertos COM disponibles:")
        for port in ports:
            print(f"- {port.device}: {port.description}")

if __name__ == "__main__":
    list_ports()
