import time
import uasyncio
from machine import Pin, I2C, SoftI2C, Timer
from sr_74hc595_bitbang import SR
from random import randrange, choice
from binascii import unhexlify
from sys import byteorder
from collections import deque
import json

## JSON-backed state, to persist through resets
class State:
    def __init__(self):
        self.config = {}
        self.load_config()
    
    def load_config(self):
        with open('./config.json') as cfg:
            self.config = json.load(cfg)
        
    def get_value(self, value):
        try:
            return self.config[value]
        except:
            return 0
    
    def save_config(self):
        with open('config.json', 'w') as cfg:
            json.dump(self.config, cfg)
    
    def set_value(self, key, value):
        self.config[key] = value
        self.save_config()

## Filtering out hysteresis to provide a more consistant UX
class Button:
    def __init__(self, pin, callback, trigger=Pin.IRQ_FALLING, repeat=300):
        self.callback = callback
        self.repeat = repeat
        self._blocked = False
        self._next_call = time.ticks_ms() + self.repeat
        pin.irq(trigger=trigger, handler=self.debounce_handler)
        
    def do_callback(self, pin):
        self.callback(pin)
            
    def debounce_handler(self, pin):
        if time.ticks_ms() > self._next_call:
            self._next_call = time.ticks_ms() + self.repeat
            self.do_callback(pin)
        
## TODO: Add support for "glitch" animations (so the displays aren't static)        
class HPDL1414:
    def __init__(self,dispnum):
        self.wr0 = Pin(12, Pin.OUT)
        self.wr1 = Pin(13, Pin.OUT)
        self.a0 = Pin(14, Pin.OUT)
        self.a1 = Pin(15, Pin.OUT)
        sr_clk = Pin(9, Pin.OUT)
        sr_latch = Pin(10, Pin.OUT)
        sr_data = Pin(11, Pin.OUT)
        self.sr = SR(sr_data, sr_clk, sr_latch)
        self.a0.value(0)
        self.a1.value(0)
        self.wr0.value(1)
        self.wr1.value(1)
        self.dispnum = dispnum
    
    def _set_addr_lines(self, pos):
        if pos == 0:
            self.a0.value(0)
            self.a1.value(0)
        elif pos == 1:
            self.a0.value(1)
            self.a1.value(0)
        elif pos == 2:
            self.a0.value(0)
            self.a1.value(1)
        elif pos == 3:
            self.a0.value(1)
            self.a1.value(1)
        
    def _get_char(self, char):
        bitstring = bin(ord(char) & 127)[2:]
        while(len(bitstring) < 7):
            bitstring = '0' + bitstring
        bitstring = ''.join(reversed(bitstring))
        bitstring = bitstring[0:5] + bitstring[6] + bitstring[5]
        return bitstring
    
    def _toggle_display(self, state):
        if self.dispnum == 0:
            self.wr0.value(state)
        else:
            self.wr1.value(state)
    
    def clear_display(self):
        for i in range(5):
            self.print_char(' ', i)
    
    def print_char(self, char, pos):
        self._set_addr_lines(pos)
        bits = self._get_char(char)
        for x in reversed(bits):
            self.sr.bit(int(x))
        self._toggle_display(0)
        self.sr.latch()
        self._toggle_display(1)


## TODO: Finish driver, add bling    
class LED_Driver:
    def __init__(self, overdrive, base_addr, i2c, color_order='RGB'):
        self.base_addr = base_addr      
        self.i2c = i2c
        self.color_order = color_order
        self.overdrive = overdrive
        self.initialize()
    
    def _byte2int(self, byteval):
        return int.from_bytes(byteval, byteorder)
    
    def _int2bytes(self, intval, numbytes):
        return intval.to_bytes(numbytes, byteorder)
    
    def _gamma_correction_8bit(self, value):
        gamma_ramp = [
                0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,
                0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  1,  1,  1,
                1,  1,  1,  1,  1,  1,  1,  1,  1,  2,  2,  2,  2,  2,  2,  2,
                2,  3,  3,  3,  3,  3,  3,  3,  4,  4,  4,  4,  4,  5,  5,  5,
                5,  6,  6,  6,  6,  7,  7,  7,  7,  8,  8,  8,  9,  9,  9, 10,
               10, 10, 11, 11, 11, 12, 12, 13, 13, 13, 14, 14, 15, 15, 16, 16,
               17, 17, 18, 18, 19, 19, 20, 20, 21, 21, 22, 22, 23, 24, 24, 25,
               25, 26, 27, 27, 28, 29, 29, 30, 31, 32, 32, 33, 34, 35, 35, 36,
               37, 38, 39, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 50,
               51, 52, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 66, 67, 68,
               69, 70, 72, 73, 74, 75, 77, 78, 79, 81, 82, 83, 85, 86, 87, 89,
               90, 92, 93, 95, 96, 98, 99,101,102,104,105,107,109,110,112,114,
              115,117,119,120,122,124,126,127,129,131,133,135,137,138,140,142,
              144,146,148,150,152,154,156,158,160,162,164,167,169,171,173,175,
              177,180,182,184,186,189,191,193,196,198,200,203,205,208,210,213,
              215,218,220,223,225,228,231,233,236,239,241,244,247,249,252,255
            ]
        
        idx = self._byte2int(value)
        return self._int2bytes(gamma_ramp[idx], 1)
    
    def _hex_to_dict(self, color):
        if '#' in color:
            color = color.lstrip('#')
        colors = [color[i:i+2] for i in range(0, len(color), 2)]
        color_triad = {
            'R': self._gamma_correction_8bit(unhexlify(colors[0])),
            'G': self._gamma_correction_8bit(unhexlify(colors[1])),
            'B': self._gamma_correction_8bit(unhexlify(colors[2]))
        }   
        return color_triad
        
    def initialize(self):
        self.i2c.writeto_mem(self.base_addr, 0, b'\b00000001')
        self.set_global_scaling('80')
        self.blank_display()
        self.set_global_brightness('32')
        self._update_ctrl_reg()
        self.i2c.writeto_mem(self.base_addr, 0, b'\01')      # normal operation
    
    def set_channel_scaling(self, channel, value):
        self.i2c.writeto_mem(self.base_addr, channel, unhexlify(value))
    
    def set_global_brightness(self, current_max):
        self.i2c.writeto_mem(self.base_addr, 110, unhexlify(current_max))
    
    async def led_selftest(self):
        for i in range(1, 70, 4):
            self.i2c.writeto_mem(self.base_addr, i, b'\xFF')
            if i > 1:
                prev = i-4
                self.i2c.writeto_mem(self.base_addr, prev, b'\x00')
            self._update_ctrl_reg()
            await uasyncio.sleep_ms(75)
            #time.sleep_ms(75)
        self.blank_display()
        return True
        
    def blank_display(self):
        for i in range(1, 72):
            self.i2c.writeto_mem(self.base_addr, i, b'\00') # blank all LEDs
            self._update_ctrl_reg()
    
    def set_global_scaling(self, value):
        for i in range (74, 109):
            self.set_channel_scaling(i, value)

    def set_led(self, channel, hexcolor):
        tgt_led_base = channel
        rgb = self._hex_to_dict(hexcolor)
        for i,v in enumerate(self.color_order):
            led_reg = tgt_led_base + (4 * i)
            #print(">> %s" % (led_reg))
            self.i2c.writeto_mem(self.base_addr, led_reg, rgb[v])
            self.i2c.writeto_mem(self.base_addr, led_reg+1, b'\00')
            self.i2c.writeto_mem(self.base_addr, led_reg+2, rgb[v])
            self.i2c.writeto_mem(self.base_addr, led_reg+3, b'\00')
            self._update_ctrl_reg()
        return led_reg
        
    def _update_ctrl_reg(self):
        self.i2c.writeto_mem(self.base_addr, 73, b'\x00')


class Pronouns:
    def __init__(self, state):
        self.state = state
        self.displays = [HPDL1414(0), HPDL1414(1)]
        self.current_pronoun = self.state.get_value('pronouns')
        self.pn_list = []
        self.load_pronouns()
        self.pn_count = len(self.pn_list) - 1
        uasyncio.run(self.animate_boot())
        self.render_pronouns()
        
    def animate_glitch(self, timer):
        glitch_chars = ['#', '*', '-', '!', '$', '%', '/', '\\', '+']
        rand_roll = randrange(20)
        if rand_roll >= 5:
            return True
        else:
#            glitch_type = randrange(2)
#            if glitch_type == 0:
#                lshifted_once = self.pnlist[self.current.pronoun
             pass       
    
    async def animate_boot(self):
        animation = ['   <', '  <<', ' <<<', '<<<<', '<<< ', '<<  ', '<   ', '    ']
        animation_tick = int(1000/self.state.get_value('animation_fps') * 5)
        
        for frame in animation:
            for x in range(2):
                for i,v in enumerate(reversed(frame)):
                    self.displays[x].print_char(v,i)
            time.sleep_ms(animation_tick)
        
    def load_pronouns(self):
        with open('/data/pronouns.json') as pnfile:
            self.pn_list = json.load(pnfile)['pronouns']
    
    def render_pronouns(self):
        for x in [0,1]:
            for i,v in enumerate(reversed(self.pn_list[self.current_pronoun][x])):
                self.displays[x].print_char(v, i)
            
    def nxt(self, pin):
        if self.current_pronoun == self.pn_count:
            self.current_pronoun = 0
        else:
            self.current_pronoun = self.current_pronoun + 1
        self.state.set_value('pronouns', self.current_pronoun)
        self.render_pronouns()
        return True
    
    def prev(self, pin):
        if self.current_pronoun == 0:
            self.current_pronoun = self.pn_count
        else:
            self.current_pronoun = self.current_pronoun - 1
        self.state.set_value('pronouns', self.current_pronoun)
        self.render_pronouns()
        return True
        
class Flags:
    def __init__(self, i2c, state):
        self.overdrive = state.get_value('overdrive_leds')
        self.current_flag = state.get_value('flag')
        self.lerp_steps = 10
        self.state = state
        self.i2c = i2c
        i2c_chips = self.i2c.scan()
        self.drvs = []
        self.fbuffer = deque((),6)
 
        if state.get_value('battery_saver') >= 1:
            self.drvs.append(LED_Driver(self.overdrive, i2c_chips[0], self.i2c, color_order=self.state.get_value("pixel_order")))
        else:
            for i in i2c_chips:
                self.drvs.append(LED_Driver(self.overdrive, i, self.i2c, color_order=self.state.get_value("pixel_order")))
        
        for i in self.drvs:
            uasyncio.run(i.led_selftest())
        self.load_flags()
        self.flag_count = len(self.flags) - 1
    
    def load_flags(self):
         with open('/data/flags.json') as flagfile:
            self.flags = json.load(flagfile)['flags']
    
    # Applies a lerp function to transition between two hex colors, at a specified percentage
    # pct should be a value between 0 and 1
    def lerp(self, color1, color2, pct, return_hex=True):
        triads = []
        for i in [color1, color2]:
            triad = self.drvs[0]._hex_to_dict(i)
            triads.append(triad)
        
        lerped = {}    
        for i in ['R', 'G', 'B']:
            c1 = self.drvs[0]._byte2int(triads[0][i])
            c2 = self.drvs[0]._byte2int(triads[1][i])
            lerped[i] = c1 + (c2-c1) * pct  
        if return_hex:
            hexed = '#'
            for i in ['R', 'G', 'B']:
                component = hex(int(lerped[i]))[2:]
                if len(component) <= 1:
                    component = '0' + component
                hexed = hexed + component
            return hexed
        else:
            return lerped


class Animation(Flags):
    def begin(self):
        self.pallete = self.flags[self.current_flag]['colors']
        self.animation = self.flags[self.current_flag]['animation']
        self.active_channels = set()
        self.current_color = 0
        self.next_color = 1
        self.last_lerp = 0
        self.lerping = False
        self.fill(self.pallete[self.current_color])
        for i in self.drvs:
            i.blank_display()
 
    def _do_fade(self):
        self.fill(self.pallete[self.current_color])
        self.current_color = self.current_color + 1
        if self.current_color >= len(self.pallete):
            self.current_color = 0
        return True

    def _do_sparkle(self):
        fill_color = ''
        pct = 0
        color2 = ''
        if self.current_color == len(self.pallete):
            self.next_color = 0
            reset = True
        else:
            self.next_color = self.current_color+1
        if self.lerping and self.animation['fade']:
            self.last_lerp += 20
            if self.last_lerp > 100:
                self.last_lerp = 100
                self.current_color = self.current_color + 1
                self.lerping = False
                if self.current_color >= len(self.pallete):
                    self.current_color = 0
                pct = self.last_lerp / 100
            if self.animation['mix'] == 1:
                color2 = self.pallete[self.next_color]
            else:
                color2 = '#000000'
            fill_color = self.lerp(self.pallete[self.current_color], color2, pct) 
        else:
            self.active_channels = set()
            self.last_lerp = 0
            self.lerping = True
            for i in range(3):
                self.active_channels.add(randrange(7))
            fill_color = self.pallete[self.current_color]
            if self.animation['fade'] == 0:
                self.current_color += 1
                if self.current_color >= len(self.pallete):
                    self.current_color = 0
                
        for i in range(7):
            for j in self.active_channels:
                if i == j:
                    self.fbuffer.append(fill_color)
                else:
                    self.fbuffer.append('#000000')
        return True
        
    def step(self, timer):
        if self.animation['style'] == 'fade':
            self._do_fade()
        elif self.animation['style'] == 'sweep':
            self._do_fade()
        elif self.animation['style'] == 'sparkle':
            self._do_sparkle()
        else:
            print("FOO")
        self.blit()
        return True
    
    def fill(self, color):
        for i in range(0,7):
            self.fbuffer.append(color)
        return True
    
    def blit(self):
        fbuffer_local = self.fbuffer
        channel = 1
        while fbuffer_local:
            v = fbuffer_local.popleft()
            for j in self.drvs:
               new_channel = j.set_led(channel, v)
            channel = new_channel+4
        return True

    def nxt(self, pin):
        if self.current_flag == self.flag_count:
            self.current_flag = 0
        else:
            self.current_flag = self.current_flag + 1
        self.state.set_value('flag', self.current_flag)
        self.begin()
        return True
    
    def prev(self, pin):
        if self.current_flag == 0:
            self.current_flag = self.flag_count
        else:
            self.current_flag = self.current_flag - 1
        self.state.set_value('flag', self.current_flag)
        self.begin()
        return True
    
    
def main():
    # Pin assignments 
    pp = Pin(16, Pin.IN, Pin.PULL_UP)
    pn = Pin(17, Pin.IN, Pin.PULL_UP)
    fp = Pin(18, Pin.IN, Pin.PULL_UP)
    fn = Pin(19, Pin.IN, Pin.PULL_UP)
    sdb = Pin(6, Pin.OUT)
    sdb.value(1)           #Enable LED Drivers
    i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=400000) #Scan i2c bus
    
    # Load Config
    state = State()
    # Main objects
    flags = Animation(i2c, state)
    pronouns = Pronouns(state)
      
    # Animation Timers
    flags.begin()
    tick = Timer()
    framerate = int(10000/state.get_value('animation_fps'))
    tick.init(period=framerate, callback=flags.step)

    if state.get_value('glitch_effects'):
        glitch = Timer()
        glitch.init(period=1000, callback=pronouns.animate_glitch)
        
    # Button interrupts
    ppirq = Button(pin=pp, callback=pronouns.prev)
    pnirq = Button(pin=pn, callback=pronouns.nxt)
    fpirq = Button(pin=fp, callback=flags.prev)
    fnirq = Button(pin=fn, callback=flags.nxt)
 
    
        
if __name__ == '__main__':
    main()