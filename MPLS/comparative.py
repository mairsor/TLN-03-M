from netmiko import ConnectHandler
from getpass import getpass
import importlib
from pathlib import Path
import yaml
import sys

# ============================================================
# Rutas
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

TOPOLOGY_FILE = "MPLS-IOU.yml"
REPORT_FILE = "comparative_report.txt"

# ============================================================
# Leer topología
# ============================================================

with open(TOPOLOGY_FILE, "r") as file:
    topology = yaml.safe_load(file)

lab_name = topology["name"]
nodes = topology["topology"]["nodes"]

devices = []

for node_name, node_data in nodes.items():

    # Solo dispositivos Cisco
    if node_data.get("kind") == "cisco_iol":

        devices.append(
            {
                "hostname": f"clab-{lab_name}-{node_name}"
            }
        )

# Ordenar (opcional)
devices.sort(key=lambda d: d["hostname"])

# ============================================================
# Credenciales
# ============================================================

username = input("Usuario SSH: ")
password = getpass("Contraseña SSH: ")

# ============================================================
# Comparación
# ============================================================

with open(REPORT_FILE, "w") as report:

    report.write("=" * 70 + "\n")
    report.write("REPORTE DE COMPARACIÓN DE CONFIGURACIONES\n")
    report.write("=" * 70 + "\n\n")

    for device in devices:

        hostname = device["hostname"]

        print(f"Conectando a {hostname}...")

        connection = ConnectHandler(
            device_type="cisco_ios",
            host=hostname,
            username=username,
            password=password,
        )

        running_config = connection.send_command(
            "show running-config"
        )

        connection.disconnect()

        # ----------------------------------------------------
        # Obtener nombre del módulo
        # ----------------------------------------------------

        module_name = hostname.replace(f"clab-{lab_name}-", "")

        try:

            modulo = importlib.import_module(
                f"scripts_configs.configs.{module_name}"
            )

        except ModuleNotFoundError:

            report.write("=" * 70 + "\n")
            report.write(f"{hostname}\n")
            report.write("No existe archivo de configuración.\n\n")
            continue

        # ----------------------------------------------------
        # Obtener automáticamente todas las listas config_*
        # ----------------------------------------------------

        expected_commands = []

        for atributo in dir(modulo):

            if atributo.startswith("config_"):

                valor = getattr(modulo, atributo)

                if isinstance(valor, list):
                    expected_commands.extend(valor)

        # ----------------------------------------------------
        # Comparación
        # ----------------------------------------------------

        missing_commands = []

        for command in expected_commands:

            command = command.strip()

            if command == "":
                continue

            if command.startswith("!"):
                continue

            if command not in running_config:
                missing_commands.append(command)

        # ----------------------------------------------------
        # Reporte
        # ----------------------------------------------------

        report.write("=" * 70 + "\n")
        report.write(f"Equipo : {hostname}\n")

        if not missing_commands:

            report.write("Estado : OK\n")
            report.write("Todos los comandos fueron encontrados.\n\n")

        else:

            report.write("Estado : DIFERENCIAS ENCONTRADAS\n")
            report.write("Comandos faltantes:\n\n")

            for cmd in missing_commands:
                report.write(f" - {cmd}\n")

            report.write("\n")

print("\nComparación finalizada correctamente.")
print(f"Reporte generado: {REPORT_FILE}")