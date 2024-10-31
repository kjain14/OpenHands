import argparse
import os
import subprocess


# Function to run shell commands
def run_command(command):
    try:
        subprocess.run(command, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f'An error occurred: {e}')


# Function to log in to Docker Hub
def docker_login():
    print('Logging into Docker Hub...')
    run_command('docker login')


# Function to process images with .eval in the name
def process_images(file_path, original_namespace, new_namespace):
    # Define testing dependencies
    dependencies = ['coverage', 'cosmic-ray']

    with open(file_path, 'r') as file:
        for line in file:
            image = line.strip()
            if '.eval' in image:
                # Ensure image is fully qualified with the original namespace
                full_image_name = (
                    f'{original_namespace}/{image}'
                    if original_namespace not in image
                    else image
                )
                print(f'Processing image: {full_image_name}')

                # Pull the original image
                run_command(f'docker pull {full_image_name}')

                # Tag the image to the new namespace
                base_name = image.split('/')[-1].replace('.eval', '')
                new_image_name = f'{new_namespace}/{base_name}'
                run_command(f'docker tag {full_image_name} {new_image_name}')

                # Create Dockerfile content dynamically
                dockerfile_content = f"""
                FROM {full_image_name}
                RUN pip install {' '.join(dependencies)}
                """

                # Write Dockerfile to a temporary file
                with open('Dockerfile.temp', 'w') as dockerfile:
                    dockerfile.write(dockerfile_content)

                # Build the new image with dependencies
                run_command(f'docker build -f Dockerfile.temp -t {new_image_name} .')

                # Push the new image to the Docker Hub
                run_command(f'docker push {new_image_name}')

                # Clean up: remove the local images and Dockerfile
                run_command(f'docker rmi {new_image_name} {full_image_name}')
                os.remove('Dockerfile.temp')


if __name__ == '__main__':
    # Set up argument parsing
    parser = argparse.ArgumentParser(
        description='Process Docker images with .eval in the name.'
    )
    parser.add_argument(
        '--images_file',
        type=str,
        required=True,
        help='Path to the file containing the list of images',
    )
    parser.add_argument(
        '--new_namespace',
        type=str,
        default='kdjain',
        help='The new Docker Hub namespace to push the images',
    )
    parser.add_argument(
        '--original_namespace',
        type=str,
        default='xingyaoww',
        help='The original Docker Hub namespace',
    )

    args = parser.parse_args()

    # Log in to Docker Hub
    docker_login()

    # Process the images
    process_images(args.images_file, args.original_namespace, args.new_namespace)
