#!/usr/bin/env python3

import pigpio
import time

pi = pigpio.pi(host='rns-md-wisun-lbr2.silabs.com')
# pi = pigpio.pi(host='10.158.122.77')
if not pi.connected:
    raise Exception("could not connect to host")

print(pi.get_pigpio_version())

# 4 is ommited because it did not want to be controlled.
bcm_gpio_list = [ 2, 3, 4, 17, 27, 22, 10, 9, 11, 5, 6, 13, 19, 26, 14, 15, 18, 23, 24, 25, 8, 7, 12, 16, 20, 21 ]

def setup_all_gpios_as_pullups(gpio_list):
    for gpio_pin in gpio_list:
        pi.set_mode(gpio_pin, pigpio.INPUT)
        pi.set_pull_up_down(gpio_pin, pigpio.PUD_UP)

def button_press(gpio_pin):
    pi.set_mode(gpio_pin, pigpio.OUTPUT)
    pi.write(gpio_pin, 0)

def button_release(gpio_pin):
    # the GPIO is setup as an input with a pull up to simulate an open collector/drain
    pi.set_mode(gpio_pin, pigpio.INPUT)
    pi.set_pull_up_down(gpio_pin, pigpio.PUD_UP)

def simulate_button_press(gpio_pin, timeout):
    button_press(gpio_pin)
    time.sleep(timeout)
    button_release(gpio_pin)


setup_all_gpios_as_pullups(bcm_gpio_list)
for gpio_pin in bcm_gpio_list:

    print(f"short press {gpio_pin}")
    simulate_button_press(gpio_pin, .25)
    print("wait for 3 seconds")
    time.sleep(3)
    print(f"short press {gpio_pin} again")
    simulate_button_press(gpio_pin, .25)
    print(f"wait for user input to move on to next GPIO pin")
    input()

pi.stop()