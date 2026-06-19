import yaml

# Archivo de topología de Containerlab
TOPOLOGY_FILE = "MPLS-IOU.yml"

# Archivo de inventario que se generará
INVENTORY_FILE = "inventory_update_script"

# Leer la topología
with open(TOPOLOGY_FILE, "r") as file:
    topology = yaml.safe_load(file)

lab_name = topology["name"]
nodes = topology["topology"]["nodes"]

# Filtrar únicamente dispositivos Cisco IOL
devices = []

for node_name, node_data in nodes.items():

    if node_data.get("kind") == "cisco_iol":
        devices.append(f"clab-{lab_name}-{node_name}")

# Ordenar alfabéticamente (opcional)
devices.sort()

# Generar inventario
with open(INVENTORY_FILE, "w") as inv:

    inv.write("[network_devices]\n")

    for device in devices:
        inv.write(f"{device}\n")

    inv.write("\n[network_devices:vars]\n")
    inv.write("ansible_user=admin\n")
    inv.write("ansible_password=admin\n")
    inv.write("ansible_network_os=cisco.ios.ios\n")
    inv.write("ansible_connection=ansible.netcommon.network_cli\n")
    inv.write("ansible_paramiko_look_for_keys=False\n")

print(f"Inventario generado correctamente: {INVENTORY_FILE}")
print(f"Dispositivos encontrados: {len(devices)}")