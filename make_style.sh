#!/bin/sh
cd "$(dirname "$0")" || exit

node scripts/check-package-installed.js postcss sass autoprefixer || exit

build_style() {
  echo "Creating $1 style..."
  cp resources/vars-$1.scss resources/vars.scss
  npx sass resources:sass_processed
  npx postcss sass_processed/style.css sass_processed/martor-description.css sass_processed/select2-dmoj.css --verbose --use autoprefixer -d $2
}

build_style 'default' 'resources'
build_style 'dark' 'resources/dark'
