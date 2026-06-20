from netmiko import ConnectHandler
from getpass import getpass
from pathlib import Path
import yaml

# ============================================================
# Rutas
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TOPOLOGY_FILE =  "MPLS-IOU.yml"
REPORT_FILE = "reporte_busqueda.txt"

# ============================================================
# Comandos a buscar
# ============================================================

ROUTER_COMMANDS = [
    "router ospf",
    "router bgp",
    "mpls ip",
    "ip cef"
]

SWITCH_COMMANDS = [
    "spanning-tree mode",
    "vlan",
    "switchport mode",
    "switchport access vlan",
    "switchport mode trunk"
]

# ============================================================
# Leer topología
# ============================================================

with open(TOPOLOGY_FILE, "r") as file:
    topology = yaml.safe_load(file)

lab_name = topology["name"]
nodes = topology["topology"]["nodes"]

devices = []

for node_name, node_data in nodes.items():

    # Ignorar PCs Linux
    if node_data.get("kind") != "cisco_iol":
        continue

    if node_data.get("type") == "l2":
        tipo = "switch"
    else:
        tipo = "router"

    devices.append({
        "hostname": f"clab-{lab_name}-{node_name}",
        "device_type": tipo
    })

devices.sort(key=lambda d: d["hostname"])

# ============================================================
# Credenciales
# ============================================================

username = input("Usuario SSH: ")
password = getpass("Contraseña SSH: ")

# ============================================================
# Reporte
# ============================================================

with open(REPORT_FILE, "w") as report:

    report.write("=" * 70 + "\n")
    report.write("REPORTE DE BÚSQUEDA DE COMANDOS\n")
    report.write("=" * 70 + "\n\n")

    for device_info in devices:

        hostname = device_info["hostname"]
        tipo = device_info["device_type"]

        print(f"Conectando a {hostname}...")

        netmiko_device = {
            "device_type": "cisco_ios",
            "host": hostname,
            "username": username,
            "password": password,
        }

        try:

            connection = ConnectHandler(**netmiko_device)

            running_config = connection.send_command(
                "show running-config"
            )

            connection.disconnect()

        except Exception as e:

            report.write("=" * 70 + "\n")
            report.write(f"Equipo : {hostname}\n")
            report.write(f"ERROR DE CONEXIÓN: {e}\n\n")

            continue

        # Seleccionar comandos según el tipo de dispositivo
        if tipo == "router":
            commands = ROUTER_COMMANDS
        else:
            commands = SWITCH_COMMANDS

        report.write("=" * 70 + "\n")
        report.write(f"Equipo : {hostname}\n")
        report.write(f"Tipo   : {tipo}\n\n")

        encontrados = 0

        for command in commands:

            if command in running_config:
                report.write(f"[OK]            {command}\n")
                encontrados += 1
            else:
                report.write(f"[NO ENCONTRADO] {command}\n")

        report.write(
            f"\nResumen: {encontrados}/{len(commands)} comandos encontrados.\n\n"
        )

print("\nBúsqueda finalizada.")
print(f"Reporte generado: {REPORT_FILE}")