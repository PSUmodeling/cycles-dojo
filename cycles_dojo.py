#!/usr/bin/env python3

import json
import pandas as pd
import numpy as np
import re
import os
import argparse

import subprocess

RESOURCES_FILE = "data/HOAResources.csv"
CROPLAND_FILE = "data/HOACropland_new.csv"
CYCLES_RUN_SCRIPT = "bin/cycles/run"
TMP_DIR = "tmp"
OUTPUT_FILE = "outputs/cycles_results.csv"
CROPS_FILE = "data/crops-horn-of-africa.crop"
SOIL_WEATHER_DIR = "data/soil_weather"

def run_cycles(params):
    cropland_df = pd.read_csv(CROPLAND_FILE)
    cropland_df.set_index(['country', 'admin1', 'admin2', 'admin3'], inplace=True)

    df = pd.read_csv(RESOURCES_FILE)
    df.set_index(['country', 'admin1', 'admin2', 'admin3'], inplace=True)
    country_soil_points = df.loc[params["country"]]

    # Run Cycles for all soil points in the country
    # - TODO: Should run in parallel
    first = True
    for index, point in country_soil_points.iterrows():

        # Get the crop fractional area for this region
        cropland_row = cropland_df.loc[params["country"], index[0], index[1], index[2]]

        try:
            crop_pd = cropland_row[params["crop_name"].lower()+"_pd"]
            crop_grain_yield = cropland_row[params["crop_name"].lower()+"_grain_yield"]
            crop_fractional_area = cropland_row[params["crop_name"].lower()+"_fractional_area"]
        except KeyError:
            crop_pd = 110
            crop_grain_yield = 1.0
            crop_fractional_area = 0.0

        # Calculate planting date
        planting_day = int(crop_pd) + int(params["start_planting_day"])
        planting_day = planting_day - 365 if planting_day > 365 else planting_day
        planting_day = planting_day + 365 if planting_day < 0 else planting_day

        # Get the input/output files
        inputfile = point["filename"]
        season_file = f"{TMP_DIR}/{inputfile}.season"
        summary_file = f"{TMP_DIR}/{inputfile}.summary"

        # ** Run Cycles **
        cmd = [CYCLES_RUN_SCRIPT,
               '-i1', f"{SOIL_WEATHER_DIR}/{inputfile}",
               '-i2', CROPS_FILE,
               '-o1', season_file,
               '-o2', summary_file,
               '-p1', params["start_year"],
               '-p2', params["end_year"],
               '-p3', params["crop_name"],
               '-p4', str(planting_day),
               '-p5', params["fertilizer_rate"],
               '-p6', params["weed_fraction"],
               '-p7', "False"
              ]
        print(cmd)
        try:
              output = subprocess.run(cmd)
        except subprocess.CalledProcessError as exc:
              print("Status : FAIL", exc.returncode, exc.output)
              continue

        # Load the output file
        exdf = get_dataframe_for_execution_result(season_file, index, params,
                                                ["grain_yield", "cum._n_stress", "actual_tr", "potential_tr"])

        # Filter/Modify/Add Columns
        exdf["crop_production"] = exdf["grain_yield"]*crop_fractional_area
        exdf["water_stress"] = 1 - exdf["actual_tr"]/exdf["potential_tr"]
        exdf["relative_yield"] = exdf["grain_yield"] / crop_grain_yield
        exdf = exdf.rename(columns={'cum._n_stress': 'nitrogen_stress'})
        exdf = exdf.drop(['actual_tr', 'potential_tr'], axis = 1)

        # Write output
        if first:
            exdf.to_csv(OUTPUT_FILE, index=False)
            first = False
        else:
            exdf.to_csv(OUTPUT_FILE, mode='a', header=False, index=False)


def load_execution_result(outputloc):
    df = pd.read_csv(outputloc, sep='\t', header=0, skiprows=[1], skipinitialspace=True)
    df = df.rename(columns=lambda x: x.strip().lower().replace(' ', '_'))
    df['date'] = pd.to_datetime(df['date'], format="%Y-%m-%d")
    return df


def get_dataframe_for_execution_result(season_file, index, params, result_fields):
    df = load_execution_result(season_file)

    # Fetch feature values
    ndf = df.filter(result_fields, axis=1)

    # Insert timestamp
    ndf.insert(0, "date", df['date']) #.values.astype(np.int64) // 10 ** 9)

    # Insert geospatial details
    ndf.insert(1, "country", params["country"])
    ndf.insert(2, "admin1", index[0] if index[0] else None)
    ndf.insert(3, "admin2", index[1] if index[1] else None)
    ndf.insert(4, "admin3", index[2] if index[2] else None)

    return ndf


def _main():
    parser = argparse.ArgumentParser(
        description="Cycles execution for a country"
    )
    parser.add_argument("--country", dest="country", default="Kenya", help="Country name")
    parser.add_argument("--crop-name", dest="crop_name", default="Maize", help="Crop name")
    parser.add_argument("--start-year", dest="start_year", default="2000", help="Simulation start year")
    parser.add_argument("--end-year", dest="end_year", default="2020", help="Simulation end year")
    parser.add_argument("--start-planting-day", dest="start_planting_day", default="103", help="Start planting date")
    parser.add_argument("--fertilizer-rate", dest="fertilizer_rate", default="50.00", help="Fertilizer rate")
    parser.add_argument("--weed-fraction", dest="weed_fraction", default="0.2", help="Weed fraction")
    args = parser.parse_args()
    run_cycles(vars(args))


if __name__ == "__main__":
    _main()
