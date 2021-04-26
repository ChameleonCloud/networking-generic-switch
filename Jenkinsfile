pipeline {
  agent any
 
  options {
    copyArtifactPermission('/neutron-kolla/*')
  }

  stages {
    stage('package') {
      steps {
        dir('dist') {
          deleteDir()
        }
        sh 'python setup.py sdist'
        sh 'find dist -type f -exec cp {} dist/networking-generic-switch.tar.gz \\;'
        archiveArtifacts(artifacts: 'dist/networking-generic-switch.tar.gz', onlyIfSuccessful: true)
      }
    }
  }
}

