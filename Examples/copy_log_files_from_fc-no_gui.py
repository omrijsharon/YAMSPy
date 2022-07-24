import os
import shutil
import argparse
import time
from datetime import datetime
from yamspy import MSPy
import functools

print = functools.partial(print, flush=True)

parser = argparse.ArgumentParser(description='Copy log files from FC')
parser.add_argument('--dst_dir', type=str, default='/home/fpvrec/Documents/flight_logs', help='Destination directory')
parser.add_argument('--extension', type=str, default='bbl', help='Extension of the files to copy')
args = parser.parse_args()

serial_port = "/dev/ttyACM0"

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
        print(f" attempt #{n_attempt} to read from FC:")
        for user in os.listdir("/media"):
            user_path = os.path.join("/media", user)
            if "BETAFLT" in os.listdir(user_path):
                beta_path = os.path.join(user_path, "BETAFLT")
                counter = 0
                while len(os.listdir(beta_path)) == 0:
                    counter += 1
                    print("Could not find any files in FC mass storage: Attempt #", counter)
                    time.sleep(1)
                    if counter > 10:
                        exception = "Could not find any files in FC mass storage"
                        print(exception)
                        return copied, exception
                file_list = [filename for filename in os.listdir(beta_path) if (filename.lower().split(".")[-1] == extension.lower() and (not "all" in filename.lower()))]
                file_list_len = len(file_list)
                if file_list_len == 0:
                    exception = f"FC flash is log files empty, 0 files with extension .{extension} were found."
                    print(exception)
                    return copied, exception
                print(f"{file_list_len} log files detected on {beta_path}")
        if file_list_len > 0:
            break
            
    if beta_path is None:
        exception = "Could not find FC mass storage"
        print(exception)
        return copied, exception

    dst_filename_list = []
    for i, file in enumerate(file_list):
        idx = str(i).zfill(2) # max of 100 logs in a batch
        dst_filename = f"batch{n_batch}log{idx}__" + datetime.now().strftime('%Y_%d_%m-%H_%M_%S')
        dst_filename_list.append(dst_filename)
        
    # Checks if FC in mass storage mode
    goggles_path = None
    not_BF_dirs = [file for file in os.listdir(user_path) if "BETAFLT" not in file]
    print("Not BetaFlight dirs: ", not_BF_dirs)
    for cur_dir in not_BF_dirs:
        if os.path.exists(os.path.join(user_path, cur_dir, "DCIM")):
            goggles_path = os.path.join(user_path, cur_dir, "DCIM", "100MEDIA")
            print("Goggles path contains ", int(len(os.listdir(goggles_path))/2), " videos")
            break
    if goggles_path is None:
        exception = "Could not find goggles SD card"
        print(exception)
        return copied, exception
    video_srt_files_list = os.listdir(goggles_path)[-2*file_list_len:]
    n_log_files = len(dst_filename_list)
    n_video_files = int(len(video_srt_files_list) / 2)
    if not n_video_files == n_log_files:
        exception = f"Number of videos ({n_video_files}) and number log-files ({n_log_files}) do not match."
        print(exception)
        return copied, exception
            

    # Copies BBL files                
    print("Copying flight log files...", file_list)
    for src_filename, dst_filename in zip(file_list, dst_filename_list):
        src_file = os.path.join(beta_path, src_filename)
        dst_file = os.path.join(dst_dir, dst_filename + ".bbl")
        shutil.copy(src_file, dst_file)
        print("Copied {} to {}".format(src_file, dst_file))
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
            print("Copied {} to {}".format(src_file, dst_file))
    copied[1] = True
    return copied, ""


if __name__ == '__main__':
    # state 0: connected, not copied --> copy
    # state 1: not connected, copied (right after copying) --> wait for 2nd connection, when connected --> erase flash
    # state 2: connected, copied, flash erased --> wait for disconnection, when disconnected --> set state 0
    state = 0
    result = [False, False]
    while True:
        try:
            with MSPy(device=serial_port, loglevel='WARNING') as board:
                fc_firmware = board.CONFIG["flightControllerIdentifier"]
                if fc_firmware == "BTFL":

                    if state == 0: # copy files
                        board.reboot(mode=board.REBOOT_TYPES['MSC'])
                        time.sleep(6)
                        master_counter = 0
                        while not all(result):
                            result, exception = copy_log_files_from_fc(args.dst_dir, args.extension)
                            time.sleep(1)
                            master_counter += 1
                            if master_counter > 10:
                                print("Could not copy log files due to " + exception)
                                break

                    elif state == 1: # erase flash
                        board.send_RAW_msg(MSPy.MSPCodes['MSP_DATAFLASH_ERASE'], data=[])
                        dataHandler = board.receive_msg()
                        board.process_recv_data(dataHandler)
                        print(datetime.now().strftime('%Y_%d_%m-%H_%M_%S'), "FC flash erased successfully.")
                        state = 2

                    elif state == 2: # wait for user do disconnect the FC
                        print(datetime.now().strftime('%Y_%d_%m-%H_%M_%S'), "Please disconnect the FC")
                        time.sleep(2)
                    	
                else:
                    print(f"Got FC firmware {fc_firmware} but expected BTFL (betaflight)")
        except:
            if state == 0:
                if all(result): # files copied
                    state = 1
            elif state == 1: # waiting for the user to reconnect the FC so its flash can be erased.
                print(datetime.now().strftime('%Y_%d_%m-%H_%M_%S'), "@ Waiting to delete FC flash...")
            elif state == 2:
                result = [False, False]
                state = 0
            print(datetime.now().strftime('%Y_%d_%m-%H_%M_%S'), "@ Waiting for FC connection...")
            time.sleep(1)
        
    
    

