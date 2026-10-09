#! /bin/bash -e

# Use this script to build, start, stop and remove HoloPi's server, in
# one container, holo-pi, on a computer without a desktop, e.g. a
# Raspberry Pi with Raspberry Pi OS Lite. Its compose project is its own,
# holo-pi: it does not touch the other containers of the computer.
#
# The container is defined in docker-compose.yml.

SERVICE=holo-pi

function display_usage() {
    echo -e "\nUsage: ./docker/dock.sh <command>\n
    Commands:
    build     Build the image
    start     Start the server in the background
    logs      Follow the output of the server
    status    Show the state of the container
    shell     Open an interactive terminal into the server's container
    stop      Stop the server
    clean     Stop the server and remove its container and image; the
              volume of the last quilt stays\n"
}

# Compose resolves the paths in docker-compose.yml against the directory that
# holds it, so every command has to run from there.
cd "$(dirname "$0")"

if [ "$#" -lt 1 ]; then
    echo "Missing required arguments."
    display_usage
    exit 1
fi

command="$1"
port=${HOLO_PI_PORT:-8095}

case "$command" in
    build)
        # Rebuilds only the layers that the Dockerfile changed since last time.
        docker compose build
        ;;
    start)
        docker compose up --detach
        echo -e "\nHoloPi is on http://$(hostname -I | awk '{print $1}'):$port"
        echo "Its API is documented on http://$(hostname -I | awk '{print $1}'):$port/docs"
        echo "Follow the output with ./docker/dock.sh logs"
        ;;
    logs)
        docker compose logs --follow $SERVICE
        ;;
    status)
        docker compose ps --all
        ;;
    shell)
        if [ -n "$(docker compose ps --quiet --status running $SERVICE)" ]; then
            docker compose exec $SERVICE bash
        else
            # Not running, e.g. because the server failed: open a terminal in a
            # fresh container of the same image to find out why.
            echo "$SERVICE is not running: opening a terminal into a new container."
            docker compose run --rm $SERVICE bash
        fi
        ;;
    stop)
        docker compose stop $SERVICE
        ;;
    clean)
        docker compose down --rmi all
        ;;
    *)
        echo "Unknown parameter: $command"
        display_usage
        exit 1
        ;;
esac
