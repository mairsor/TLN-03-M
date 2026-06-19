from devices import devices

ARCHIVO = "inventory_update_script"

with open(ARCHIVO, "w") as f:

    # Grupo
    f.write("[MPLS_routers]\n")

    for device in devices:
        f.write(f"{device}\n")

    # Variables comunes
    f.write("\n[MPLS_routers:vars]\n")
    f.write("ansible_user=admin\n")
    f.write("ansible_password=admin\n")
    f.write("ansible_network_os=cisco.ios.ios\n")
    f.write("ansible_connection=ansible.netcommon.network_cli\n")
    f.write("ansible_paramiko_look_for_keys=False\n")

print(f"Inventario generado correctamente: {ARCHIVO}")