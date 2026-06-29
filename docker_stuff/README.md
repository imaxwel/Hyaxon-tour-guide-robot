# Tourbot Docker simulation environment

This directory contains the local Docker Compose setup for CPU plus Mesa
integrated graphics. It intentionally does not enable NVIDIA/CUDA by default.

## Host setup

From the repository root:

```bash
chmod +x docker_stuff/setup-host.bash
./docker_stuff/setup-host.bash
```

The setup script writes the LAN proxy to `docker_stuff/.env` by default:

```text
http://192.168.100.8:34601
```

Override it when needed:

```bash
TOURBOT_PROXY=http://proxy-host:port ./docker_stuff/setup-host.bash
```

If GUI forwarding fails and `docker_stuff/.xauth` is empty, allow the local
user temporarily:

```bash
xhost +SI:localuser:"$(id -un)"
```

## Build and start

First run, or after changing the Dockerfile / image dependencies:

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d --build sim
```

Normal daily start after the image already exists:

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml up -d sim
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml exec sim bash
```

## Build the ROS workspace

Inside the container:

```bash
cd /workspace
source /opt/ros/jazzy/setup.bash
rosdep update --rosdistro jazzy
sudo apt-get update
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy -t buildtool -t build -t exec
colcon build --symlink-install
source install/setup.bash
```

The `-t` flags install build and runtime dependencies while skipping test-only
dependencies. This avoids pulling lint/test packages that are not required for
the simulator container.

## Validate GUI and OpenGL

Inside the container:

```bash
xeyes
glxinfo -B
rviz2
```

`rviz2` may show missing TF/map warnings until the simulator is running.
On this host the Intel iGPU path uses `MESA_LOADER_DRIVER_OVERRIDE=iris`,
which is written to `docker_stuff/.env` by the setup script.

## Run simulation

Default lightweight project simulation. This starts Gazebo with the
`cardboard_city` world, TurtleBot4, Gazebo bridges, and base robot nodes. It
does not start RViz, AMCL, or Nav2 unless requested:

```bash
ros2 launch tourbot_bringup sim.launch.py
```

Full navigation stack with RViz:

```bash
ros2 launch tourbot_bringup sim.launch.py localization:=true nav2:=true rviz:=true
```

Use the upstream TurtleBot4 warehouse instead of the project world:

```bash
ros2 launch tourbot_bringup sim.launch.py use_custom_sim:=false
```

Override the project world or map paths when needed:

```bash
WORLD_STEM="$(ros2 pkg prefix --share tourbot_bringup)/worlds/cardboard_city/world"
MAP_YAML="$(ros2 pkg prefix --share tourbot_bringup)/maps/cardboard_city/map_area.yaml"

ros2 launch tourbot_bringup sim.launch.py \
  use_custom_sim:=true \
  custom_world:="$WORLD_STEM" \
  custom_map:="$MAP_YAML" \
  localization:=true \
  nav2:=true \
  rviz:=true
```

## Stop

```bash
docker compose --env-file docker_stuff/.env -f docker_stuff/compose.sim.yaml down
```
