"""Entry point for tuiredis: python -m tuiredis"""

from __future__ import annotations

import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="tuiredis",
        description="TRedis — A beautiful Redis TUI client",
    )
    parser.add_argument("-H", "--host", default="127.0.0.1", help="Redis host (default: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, default=6379, help="Redis port (default: 6379)")
    parser.add_argument("-a", "--password", default=None, help="Redis password")
    parser.add_argument("-n", "--db", type=int, default=0, help="Redis database number (default: 0)")
    parser.add_argument("-c", "--connect", action="store_true", help="Auto-connect on startup")

    # Cluster Arguments
    parser.add_argument("--cluster", action="store_true", help="Connect using Redis Cluster mode")

    # Sentinel Arguments
    parser.add_argument("--sentinel", action="store_true", help="Connect via Redis Sentinel master discovery")
    parser.add_argument(
        "--sentinel-node",
        action="append",
        default=None,
        help="Redis Sentinel node in host[:port] form; may be passed multiple times",
    )
    parser.add_argument("--sentinel-host", default=None, help="Redis Sentinel host")
    parser.add_argument("--sentinel-port", type=int, default=26379, help="Redis Sentinel port (default: 26379)")
    parser.add_argument("--sentinel-master", default=None, help="Redis Sentinel master name")
    parser.add_argument("--sentinel-password", default=None, help="Redis Sentinel password")

    # SSH Arguments
    parser.add_argument("--ssh-host", default=None, help="SSH Server host for tunneling")
    parser.add_argument("--ssh-port", type=int, default=22, help="SSH Server port (default: 22)")
    parser.add_argument("--ssh-user", default=None, help="SSH Username")
    parser.add_argument("--ssh-password", default=None, help="SSH Password")
    parser.add_argument("--ssh-key", default=None, help="SSH Private Key path")

    args = parser.parse_args()

    from tuiredis.app import TRedisApp

    app = TRedisApp(
        host=args.host,
        port=args.port,
        password=args.password,
        db=args.db,
        auto_connect=args.connect,
        use_cluster=args.cluster,
        use_sentinel=args.sentinel,
        sentinel_nodes=",".join(args.sentinel_node) if args.sentinel_node else None,
        sentinel_host=args.sentinel_host,
        sentinel_port=args.sentinel_port,
        sentinel_master_name=args.sentinel_master,
        sentinel_password=args.sentinel_password,
        ssh_host=args.ssh_host,
        ssh_port=args.ssh_port,
        ssh_user=args.ssh_user,
        ssh_password=args.ssh_password,
        ssh_private_key=args.ssh_key,
    )
    app.run()


if __name__ == "__main__":
    main()
