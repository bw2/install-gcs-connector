import glob
import os
from setuptools import setup
from setuptools.command.install import install
import socket
import urllib.request

from pyspark.find_spark_home import _find_spark_home

GCS_CONNECTOR_URL = 'https://repo1.maven.org/maven2/com/google/cloud/bigdataoss/gcs-connector/hadoop2-1.9.17/gcs-connector-hadoop2-1.9.17-shaded.jar'

def is_dataproc_VM():
    """Check if this installation is being executed on a Google Compute Engine dataproc VM"""
    try:
        dataproc_metadata = urllib.request.urlopen("http://metadata.google.internal/0.1/meta-data/attributes/dataproc-bucket").read()
        if dataproc_metadata.decode("UTF-8").startswith("dataproc"):
            return True
    except:
        pass
    return False
    
    
class PostInstallCommand(install):

    def run(self):
        install.run(self)
        
        if is_dataproc_VM():
            self.announce("Running on a Dataproc VM which should already have the GCS cloud connector installed.", level=3)
            return  # cloud connector is installed automatically on dataproc VMs 

        spark_home = _find_spark_home()

        # download GCS connector jar
        local_jar_path = os.path.join(spark_home, "jars", os.path.basename(GCS_CONNECTOR_URL))
        try:
            self.announce("Downloading %s to %s" % (GCS_CONNECTOR_URL, local_jar_path), level=3)
            urllib.request.urlretrieve(GCS_CONNECTOR_URL, local_jar_path)
        except Exception as e:
            self.warn("Unable to download GCS connector to %s. %s" % (local_jar_path, e))
            return

        # look for existing key files in ~/.config. 
        key_file_regexps = [
            "~/.config/gcloud/application_default_credentials.json", 
            "~/.config/gcloud/legacy_credentials/*/adc.json",
        ]
        # if more than one file matches a glob pattern, select the newest.
        key_file_sort = lambda file_path: -1 * os.path.getctime(file_path)          
        key_file_path = None
        for key_file_regexp in key_file_regexps:
            paths = sorted(glob.glob(os.path.expanduser(key_file_regexp)), key=key_file_sort)
            if paths:            
                key_file_path = next(iter(paths))
                self.announce("Using key file: %s" % key_file_path, level=3)
                break
        else:
            self.error("No keys found in these locations: \n%s." % (", ".join(key_file_regexps), e))
            self.error("Run \n\n  gcloud auth application-default login \n\n")
            self.error("Then reinstall with: \n\n  python3 -m pip install -vvv --upgrade git+https://github.com/bw2/install-gcs-connector.git \n\n")
            return

        # update spark-defaults.conf
        spark_config_dir = os.path.join(spark_home, "conf")
        if not os.path.exists(spark_config_dir):
            os.mkdir(spark_config_dir)
        spark_config_file_path = os.path.join(spark_config_dir, "spark-defaults.conf")
        self.announce("Setting json.keyfile to %s in %s" % (key_file_path, spark_config_file_path), level=3)

        spark_config_lines = [
            "spark.hadoop.google.cloud.auth.service.account.enable true\n",
            "spark.hadoop.google.cloud.auth.service.account.json.keyfile %s\n" % key_file_path,
        ]
        try:
            if os.path.isfile(spark_config_file_path):
                with open(spark_config_file_path, "rt") as f:
                    for line in f:
                        if "spark.hadoop.google.cloud.auth.service.account.enable" in line:
                            continue
                        if "spark.hadoop.google.cloud.auth.service.account.json.keyfile" in line:
                            continue

                        spark_config_lines.append(line)

            with open(spark_config_file_path, "wt") as f:
                for line in spark_config_lines:
                    f.write(line)

        except Exception as e:
            self.warn("Unable to update spark config %s. %s" % (spark_config_file_path, e))
            return

setup(
    name='install-gcs-connector',
    url='https://github.com/bw2/install-gcs-connector',
    author='Ben',
    author_email='ben.weisburd@gmail.com',
    install_requires=['hail'],
    version='0.1',
    license='MIT',
    description='Automates the installation of the Google Cloud Storage connector for hadoop as described in https://github.com/GoogleCloudDataproc/hadoop-connectors/blob/master/gcs/INSTALL.md',
    cmdclass={
        'install': PostInstallCommand,
    },
)
