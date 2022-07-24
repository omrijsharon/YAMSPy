import os
import shutil
import argparse
import time
from datetime import datetime
from yamspy import MSPy
# from utils.mspy import MSPy
from tkinter import *
import serial.tools.list_ports


parser = argparse.ArgumentParser(description='Copy log files from FC')
parser.add_argument('--dst_dir', type=str, default='/home/fpvrec/Documents/flight_logs', help='Destination directory')
parser.add_argument('--extension', type=str, default='bbl', help='Extension of the files to copy')
args = parser.parse_args()

serial_port = "/dev/ttyACM0"

def get_bf_port():
    for port, desc, hwid in sorted(serial.tools.list_ports.comports()):
        print("{}: {} [{}]".format(port, desc, hwid))
        if "betaflight" in desc.lower():
            return port
    raise ConnectionError("No Betaflight FC found")


def copy_log_files_from_fc(dst_dir, extension='bbl'):
    """
    Copy log files from FC to local machine.
    """
    dst_dir = os.path.join(dst_dir, datetime.now().strftime('%Y_%m_%d'))
    os.path.exists(dst_dir) or os.makedirs(dst_dir)
    n_batch = str(len(os.listdir(dst_dir))).zfill(4) #max of 10000 batches a day
    dst_dir = os.path.join(dst_dir, n_batch)
    os.makedirs(dst_dir)
    copied = [False, False]
    # Checks if FC in mass storage mode
    beta_path = None
    file_list_len = 0
    for n_attempt in range(10):
        time.sleep(1)
        txt = f" attempt #{n_attempt} to read from FC:"
        lbl.configure(text=txt)
        for user in os.listdir("/media"):
            user_path = os.path.join("/media", user)
            if "BETAFLT" in os.listdir(user_path):
                beta_path = os.path.join(user_path, "BETAFLT")
                counter = 0
                while len(os.listdir(beta_path)) == 0:
                    counter += 1
                    txt = f"Could not find any files in FC mass storage:\nAttempt #{counter}"
                    lbl.configure(text=txt)
                    time.sleep(1)
                    if counter > 10:
                        exception = "Could not find any files in FC mass storage"
                        lbl.configure(text=exception)
                        return copied, exception
                file_list = [filename for filename in os.listdir(beta_path) if (filename.lower().split(".")[-1] == extension.lower() and (not "all" in filename.lower()))]
                file_list_len = len(file_list)
                if file_list_len == 0:
                    exception = f"FC flash is log files empty,\n0 files with extension .{extension} were found."
                    lbl.configure(text=exception)
                    return copied, exception
                txt = f"{file_list_len} log files detected on {beta_path}"
                lbl.configure(text=txt)
        if file_list_len > 0:
            break
            
    if beta_path is None:
        exception = "Could not find FC mass storage"
        lbl.configure(text=exception)
        return copied, exception

    dst_filename_list = []
    for i, file in enumerate(file_list):
        idx = str(i).zfill(2) # max of 100 logs in a batch
        dst_filename = f"batch{n_batch}log{idx}__" + datetime.now().strftime('%Y_%d_%m-%H_%M_%S')
        dst_filename_list.append(dst_filename)
        
    # Checks if FC in mass storage mode
    goggles_path = None
    not_BF_dirs = [file for file in os.listdir(user_path) if "BETAFLT" not in file]
    txt = f"Not BetaFlight dirs: {not_BF_dirs}"
    lbl.configure(text=txt)
    for cur_dir in not_BF_dirs:
        if os.path.exists(os.path.join(user_path, cur_dir, "DCIM")):
            goggles_path = os.path.join(user_path, cur_dir, "DCIM", "100MEDIA")
            txt = "Goggles path contains " + str(int(len(os.listdir(goggles_path))/2)) + " videos"
            lbl.configure(text=txt)
            break
    if goggles_path is None:
        exception = "Could not find goggles SD card"
        lbl.configure(text=exception)
        return copied, exception
    video_srt_files_list = os.listdir(goggles_path)[-2*file_list_len:]
    n_log_files = len(dst_filename_list)
    n_video_files = int(len(video_srt_files_list) / 2)
    if not n_video_files == n_log_files:
        exception = f"Number of videos ({n_video_files}) and\n number log-files ({n_log_files}) do not match."
        lbl.configure(text=exception)
        return copied, exception
            

    # Copies BBL files                
    txt = "Copying flight log files..." + str(file_list)
    lbl.configure(text=txt)
    for src_filename, dst_filename in zip(file_list, dst_filename_list):
        src_file = os.path.join(beta_path, src_filename)
        dst_file = os.path.join(dst_dir, dst_filename + ".bbl")
        shutil.copy(src_file, dst_file)
        txt = "Copied {}\n to {}".format(src_file, dst_file)
        lbl.configure(text=txt)
        copied[0] = True

    # Copies MP4 and SRT files                
    for n, dst_file in enumerate(dst_filename_list):
        even = 2 * n
        odd = 2 * n + 1
        for k in [even, odd]:
            src_filename = video_srt_files_list[k]
            src_extension = src_filename.split(".")[-1]
            dst_filename = dst_file + "." + src_extension
            src_file = os.path.join(goggles_path, src_filename)
            dst_file = os.path.join(dst_dir, dst_filename)
            shutil.copy(src_file, dst_file)
            txt = "Copied {}\n to {}".format(src_file, dst_file)
            lbl.configure(text=txt)
    copied[1] = True
    return copied, ""


def Refresher():
    inner_loop()
    window.after(1000, Refresher)


def inner_loop():
    # txt = btn.cget('text')
    # btn['text'] = str(int(txt)+1)
    # txt = btn.cget('text')
    # lbl.configure(text=txt)

    state = IntVar()
    state.set(0)
    # state 0: connected, not copied --> copy
    # state 1: not connected, copied (right after copying) --> wait for 2nd connection, when connected --> erase flash
    # state 2: connected, copied, flash erased --> wait for disconnection, when disconnected --> set state 0
    result = BooleanVar()
    result.set(False)
    # result = [False, False]
    try:
        with MSPy(device=serial_port, loglevel='WARNING') as board:
            fc_firmware = board.CONFIG["flightControllerIdentifier"]
            if fc_firmware == "BTFL":

                if state.get() == 0:  # copy files
                    board.reboot(mode=board.REBOOT_TYPES['MSC'])
                    time.sleep(6)
                    master_counter = 0
                    while not result.get():
                        is_copied, exception = copy_log_files_from_fc(args.dst_dir, args.extension)
                        result.set(all(is_copied))
                        time.sleep(1)
                        master_counter += 1
                        if master_counter > 10:
                            txt = "Could not copy log files due to \n" + exception
                            lbl.configure(text=txt)
                            break

                elif state.get() == 1:  # erase flash
                    board.send_RAW_msg(MSPy.MSPCodes['MSP_DATAFLASH_ERASE'], data=[])
                    dataHandler = board.receive_msg()
                    board.process_recv_data(dataHandler)
                    txt = datetime.now().strftime('%Y_%d_%m-%H_%M_%S') + "\nFC flash erased successfully."
                    lbl.configure(text=txt)
                    state.set(2)

                elif state.get() == 2:  # wait for user do disconnect the FC
                    txt = datetime.now().strftime('%Y_%d_%m-%H_%M_%S') + "\nPlease disconnect the FC"
                    lbl.configure(text=txt)
                    time.sleep(2)

            else:
                txt = f"Got FC firmware {fc_firmware} \nbut expected BTFL (betaflight)"
                lbl.configure(text=txt)
    except Exception as e:
        if state.get() == 0:
            if result.get():  # files copied
                state.set(1)
        elif state.get() == 1:  # waiting for the user to reconnect the FC so its flash can be erased.
            txt = datetime.now().strftime('%Y_%d_%m-%H_%M_%S') + "\n Waiting to delete FC flash..."
            lbl.configure(text=txt)
        elif state.get() == 2:
            result.set(False)
            state.set(0)
        txt = datetime.now().strftime('%Y_%d_%m-%H_%M_%S') + "\n Waiting for FC connection..."
        lbl.configure(text=txt)


if __name__ == '__main__':
    window = Tk()
    window.title("Zazu Data Box")
    window.geometry('480x280')
    lbl = Label(window, text="Zazu Data Box", font=("Arial Bold", 18))
    lbl.place(x=20, y=80)
    Refresher()
    window.mainloop()
        
    
    

