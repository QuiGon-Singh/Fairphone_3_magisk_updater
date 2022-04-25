import argparse, hashlib, os, re, subprocess, sys
from datetime import datetime
from threading import Thread
from time import sleep
from url_check import url_check


def only_one_phone():

    command = ['adb', 'devices']

    phone_count_check = subprocess.run(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    stdout_message = phone_count_check.stdout.decode()
    message_clean = stdout_message.replace('List of devices attached\n', '')[:-2]

    phone_count = re.findall(re.compile('(.*?)\tdevice'), message_clean)

    if len(phone_count) == 0:
        logger.critical('No phone found')
    elif len(phone_count) == 1:
        logger.info(f'One device found - ID: \'{phone_count[0]}\'')
    else:
        logger.critical('Multiple devices found - try again with only one device')


def fairphone_current_version():

    command = ['adb', 'shell', 'getprop', 'ro.system.build.date']

    patch_check = subprocess.run(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)

    stdout_message = patch_check.stdout.decode().strip()

    build_month, build_day, build_year = re.findall(re.compile('.*? (.*?) (\d{1,2}) \d\d:\d\d:\d\d .*? (\d{4})'), stdout_message)[0]
    build_date = datetime.strptime(f'{build_day} {build_month} {build_year}', '%d %b %Y').date()

    logger.info(f'Fairphone\'s current build: {build_date}')

    return(build_date)


def available_builds(fairphone_build):

    logger.info('Finding available builds')

    base_url = 'https://download.lineageos.org/FP3'
    html_response = url_check(base_url, logger)

    table_of_links = html_response.html.find('tbody', first = True)
    latest_build_row = table_of_links.find('tr', first = True)

    latest_build_date_cell = latest_build_row.find('td')[-1]
    latest_build_date = datetime.strptime(latest_build_date_cell.text, '%Y-%m-%d').date()

    logger.info(f'Found recovery for: {latest_build_date}')

    latest_recovery_image_link = latest_build_row.find('a')[2].attrs['href']
    latest_recovery_checksum_link = latest_build_row.find('a')[3].attrs['href']

    return(latest_recovery_image_link, latest_recovery_checksum_link)


def check_directory(magisk_directory):

    directory_check = os.path.isdir(magisk_directory)

    if directory_check == False:
        sys.exit(f'Cannot reach directory {directory_check}')

    os.chdir(magisk_directory)


def download_file(url, dict_url, type_file):
    import requests

    build_filename = url.split('/')[-1]

    with open(build_filename, 'wb') as downloading_file:
        r = requests.get(url, stream = True)
        for chunk in r.iter_content(chunk_size = 1024):
            if chunk:
                downloading_file.write(chunk)

    downloaded_file = os.path.abspath(build_filename)

    dict_url[type_file]['file'] = downloaded_file

    return(downloaded_file)


def download_waiting(message):    # Defines a function which prints out a message to the same line which will be used whilst the program is busy.
    print(message, end = '\r')
    sleep(1)
    print(message + '.', end = '\r')
    sleep(1)
    print(message + '..', end = '\r')
    sleep(1)
    print(message + '...', end = '\r')
    sleep(1)
    print(message + '....', end = '\r')
    print(message + '                       ', end = '\r')


def file_expected_checksum(url):

    response_html = url_check(url, logger)
    expected_checksum = re.findall(re.compile('(.*?)  lineage.*?.[zip|img]'), response_html.text)[0]

    return(expected_checksum)


def compare_checksum(file_to_check, expected_checksum):

    with open(file_to_check, 'rb') as hashing_file:
        file_bytes = hashing_file.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        if file_hash == expected_checksum:
            logger.info('The SHA256 hash for downloaded file matches expected hash')
            return(True)
        else:
            logger.warning('The SHA256 hash for downloaded file does not match expected hash. Re-downloading')
            return(False)


def download_updates(update_recovery_link, update_recovery_checksum):

    files_dict = {'build': {},
                           'recovery': {}}

    logger.info('Downloading new recovery file')

    new_recovery_checksum = file_expected_checksum(update_recovery_checksum)
    new_recovery_download_verdict = False

    while new_recovery_download_verdict == False:
        t_recovery = Thread(target = download_file, args = [update_recovery_link, files_dict, 'recovery'])
        t_recovery.start()
        while t_recovery.is_alive():
            download_waiting('Downloading new recovery')

        new_recovery_download_verdict = compare_checksum(files_dict['recovery']['file'], new_recovery_checksum)

    return(files_dict)


def transfer_recovery_file(files_dict):

    recovery_file = files_dict['recovery']['file']

    logger.info('Sending recovery file to Fairphone')

    target_directory = '/storage/emulated/0/Download/'

    command = ['adb', 'push', recovery_file, target_directory]
    subprocess.run(command, stdout = subprocess.PIPE)

    file_name = recovery_file.split('/')[-1]

    logger.info(f'Recovery file found in Fairphone: {target_directory}{file_name}')

    _ = input('Apply Magisk patch to recovery file.\nPress Enter when done')

    return(file_name)


def check_for_patch_file():

    command = ['adb', 'shell', 'ls', f'/storage/emulated/0/Download/magisk_patched-*']
    patch_check = subprocess.run(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)

    stdout_message = patch_check.stdout.decode()

    find_match = re.findall(re.compile('/storage/emulated/0/Download/magisk_patched-(\d{5}_.+?).img'), stdout_message)

    if len(find_match) == 1:
        logger.info(f'File found on Fairphone. Suffix "{find_match[0]}"')
        return(find_match[0])
    elif len(find_match):
        logger.critical('Found {len(find_match)} potential files. Delete all unwanted files')
        LogWriter.end(logger)
        sys.exit()
    elif len(find_match) == 0:
        logger.critical('File could not be found on Fairphone.')
        LogWriter.end(logger)
        sys.exit()


def pull_patched_file(file_suffix):

    command = ['adb', 'pull', f'/storage/emulated/0/Download/magisk_patched-{file_suffix}.img']
    subprocess.run(command)


def check_downloaded_file(lineageos_directory, file_suffix):

    file_to_check = f'magisk_patched-{file_suffix}.img'
    check_file = os.path.isfile(os.path.join(lineageos_directory), file_to_check)

    if check_file == False:
        logger.critical('File not found in directory {file_to_check}')

    return(file_to_check)


def reboot_to_recovery():

    logger.info('Rebooting Fairphone into recovery mode')
    command = ['adb', 'reboot', 'recovery']
    subprocess.run(command)

    _ = input('User: prepare Fairphone for ADB sideload')


def sideload_update(files_dict):

    boot_file = files_dict['build']['file']

    logger.info('Sideloading new build')

    command = ['adb', 'sideload', boot_file]
    subprocess.run(command, stdout = subprocess.PIPE)

    logger.info(f'Sideload complete')


def reboot_normally():

    logger.info('Rebooting Fairphone to normal mode')
    command = ['fastboot', 'reboot']
    subprocess.run(command)


def check_if_in_bootloader():

    command = ['fastboot', 'devices']
    bootloader_mode_check = subprocess.run(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)

    stdout_message = bootloader_mode_check.stdout.decode()

    pattern_match = re.match(re.compile('.*?\tfastboot\n\n'), stdout_message)

    if pattern_match:
        return(True)
    else:
        return(False)


def reboot_to_bootloader():

    logger.info('Rebooting Fairphone into bootloader mode')
    command = ['adb', 'reboot', 'bootloader']
    subprocess.run(command)


def flash_boot_img(file_suffix):

    logger.info('Waiting for bootloader')

    in_bootloader = False
    while in_bootloader == False:
        sleep(5)
        in_bootloader = check_if_in_bootloader()

    for boot_partition in ['boot_b', 'boot_a']:
        command = ['fastboot', 'flash', boot_partition, f'magisk_patched-{file_suffix}.img']
        logger.info(f'Patching {boot_partition}')
        subprocess.run(command)


def check_if_in_normal_boot_mode():

    command = ['adb', 'devices']

    phone_count_check = subprocess.run(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    stdout_message = phone_count_check.stdout.decode()
    message_clean = stdout_message.replace('List of devices attached\n', '')

    pattern_match = re.match(re.compile('.*?\tdevice\n\n'), message_clean)

    if pattern_match:
        return(True)
    else:
        return(False)


def patch_file_cleanup(file_suffix, recovery_file, fairphone_build_date):

    # _ = input('User: Press Enter when Fairphone has booted to normal mode')
    normal_boot_mode = False
    while normal_boot_mode == False:
        sleep(20)
        normal_boot_mode = check_if_in_normal_boot_mode()

    magisk_file = f'/storage/emulated/0/Download/magisk_patched-{file_suffix}.img'
    recovery_file_full = f'/storage/emulated/0/Download/{recovery_file}'

    logger.info(f'Deleting patched file with suffix "{file_suffix}"')
    command = ['adb', 'shell', 'rm', '-f', magisk_file]
    subprocess.run(command)

    logger.info(f'Deleting recovery file for date {fairphone_build_date}')
    command = ['adb', 'shell', 'rm', '-f', recovery_file_full]
    subprocess.run(command)


if __name__ == '__main__':

    sys.path.append('/home/gurpreet/git')
    from LogWriter import LogWriter

    working_directory = '/home/gurpreet/Downloads/lineageos/'

    check_directory(working_directory)

    logger = LogWriter.log_writer(working_directory)
    LogWriter.start(logger)

    logger.info(f'Changed directory to {working_directory}')

    only_one_phone()
    fairphone_build_date = fairphone_current_version()
    update_recovery_link, update_recovery_checksum = available_builds(fairphone_build_date)

    update_files_dict = download_updates(update_recovery_link, update_recovery_checksum)

    recovery_file_to_cleanup = transfer_recovery_file(update_files_dict)
    found_file_suffix = check_for_patch_file()
    pull_patched_file(found_file_suffix)

    reboot_to_bootloader()
    flash_boot_img(found_file_suffix)
    reboot_normally()
    patch_file_cleanup(found_file_suffix, recovery_file_to_cleanup, fairphone_build_date)

    LogWriter.end(logger)
