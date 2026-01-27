# Leon's PiCar Brain

AI-powered robot car for Leon.

## Setup

The Pi auto-syncs from this repo every minute. Push changes here, the car updates automatically.

## Files

- `keys.py` - API credentials (don't commit real keys)
- `leon_modes.py` - Custom fun modes for Leon

## Usage

SSH into the car:
```bash
ssh pi@picar.local
# Password: Leon
```

Run the setup (first time only):
```bash
./setup-picar.sh
```

Run voice assistant:
```bash
source ~/picar-venv/bin/activate
cd ~/picar-x/gpt_examples
sudo ~/picar-venv/bin/python3 gpt_car.py
```
