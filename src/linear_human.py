#!/usr/bin/env python

import rospy
import numpy as np
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion
from visualization_msgs.msg import Marker, MarkerArray
import time
import sys

class LinearHuman(object):	
	"""
	This class simulates mocap data of a human moving around a space.
	The human always moves in a straight line from start to goal, 
	regardless of the environment or obstacles. 
	"""

	def __init__(self):

		rospy.init_node('linear_human', anonymous=True)

		# load all the prediction params and setup subscriber/publishers
		self.load_parameters()
		self.register_callbacks()

		#make a marker array for all the goals
		marker_array = MarkerArray()
		for g in self.real_goals:
			marker = self.state_to_marker(xy=g, color=self.color)
			marker_array.markers.append(marker)

		# Re-number the marker IDs
		id = 0
		for m in marker_array.markers:
			m.id = id
			id += 1

		rate = rospy.Rate(100)

		while not rospy.is_shutdown():
			t = rospy.Time.now().secs - self.start_T
			self.update_pose(t)
			self.state_pub.publish(self.human_pose)
			self.marker_pub.publish(self.pose_to_marker(color=self.color))
			self.goal_pub.publish(marker_array)
			rate.sleep()

	def load_parameters(self):
		"""
		Loads all the important paramters of the human sim
		"""
		# store which human occu grid we are computing
		self.human_number = str(rospy.get_param("human_number"))

		# --- real-world params ---# 

		low = rospy.get_param("state/lower"+self.human_number)
		up = rospy.get_param("state/upper"+self.human_number)

		# get real-world measurements of experimental space
		self.real_height = up[1] - low[1] 
		self.real_width = up[0] - low[0] 
		self.real_lower = low
		self.real_upper = up

		# (real-world) start and goal locations 
		self.real_start = rospy.get_param("pred/human"+self.human_number+"_real_start")
		self.real_goals = rospy.get_param("pred/human"+self.human_number+"_real_goals")

		# color to use to represent this human
		self.color = rospy.get_param("pred/human"+self.human_number+"_color")

		self.start_T = rospy.Time.now().secs
		self.final_T = 60.0
		self.step_time = self.final_T/(len(self.real_goals)+1) 
		self.waypt_times = [i*self.step_time for i in range(len(self.real_goals)+2)] # include start and end
		self.human_pose = None

		# --- simulation params ---# 
		
		# measurements of gridworld 
		self.sim_height = int(rospy.get_param("pred/sim_height"+self.human_number))
		self.sim_width = int(rospy.get_param("pred/sim_width"+self.human_number))

		# resolution (real meters)/(sim dim-1) (m/cell)
		self.res_x = self.real_width/(self.sim_width-1)
		self.res_y = self.real_height/(self.sim_height-1)

		self.human_height = rospy.get_param("pred/human_height")

		self.prev_pose = self.real_start

	def register_callbacks(self):
		"""
		Sets up all the publishers/subscribers needed.
		"""
		self.goal_pub = rospy.Publisher('/goal_markers'+self.human_number, MarkerArray, queue_size=10)
		self.state_pub = rospy.Publisher('/human_pose'+self.human_number, PoseStamped, queue_size=10)
		self.marker_pub = rospy.Publisher('/human_marker'+self.human_number, Marker, queue_size=10)

	def state_to_marker(self, xy=[0,0], color=[1.0,0.0,0.0]):
		"""
		Converts xy position to marker type to vizualize human
		"""
		marker = Marker()
		marker.header.frame_id = "/world"
		marker.header.stamp = rospy.Time().now()

		marker.type = marker.SPHERE
		marker.action = marker.ADD
		marker.pose.orientation.w = 1
		marker.pose.position.z = 0
		marker.scale.x = self.res_x
		marker.scale.y = self.res_y
		marker.scale.z = self.res_x
		marker.color.a = 1.0
		marker.color.r = color[0]
		marker.color.g = color[1]
		marker.color.b = color[2]

		marker.pose.position.x = xy[0]
		marker.pose.position.y = xy[1]

		return marker

	def pose_to_marker(self, color=[1.0, 0.0, 0.0]):
		"""
		Converts pose to marker type to vizualize human
		"""
		marker = Marker()
		marker.header.frame_id = "/world"

		marker.type = marker.CUBE
		marker.action = marker.ADD
		marker.pose.orientation.w = 1
		marker.pose.position.z = 0.1
		marker.scale.x = self.res_x
		marker.scale.y = self.res_y
		marker.scale.z = self.human_height
		marker.color.a = 1.0		
		marker.color.r = color[0]
		marker.color.g = color[1]
		marker.color.b = color[2]


		if self.human_pose is not None:
			marker.pose.position.x = self.human_pose.pose.position.x 
			marker.pose.position.y = self.human_pose.pose.position.y
			marker.pose.position.z = marker.scale.z/2.0
		else:
			marker.pose.position.x = 0
			marker.pose.position.y = 0
			marker.pose.position.z = 2

		return marker

	def update_pose(self, curr_time):
		"""
		Gets the next desired position along trajectory
		by interpolating between waypoints given the current t.
		"""

		# for now, human trajectory always returns back to start
		waypts = [self.real_start] + self.real_goals + [self.real_start]
		if curr_time >= self.final_T:
			target_pos = np.array(self.real_start)
		else:
			curr_waypt_idx = int(curr_time/self.step_time)
			prev = np.array(waypts[curr_waypt_idx])
			next = np.array(waypts[curr_waypt_idx+1])		
			ti = self.waypt_times[curr_waypt_idx]
			tf = self.waypt_times[curr_waypt_idx+1]
			target_pos = (next - prev)*((curr_time-ti)/(tf - ti)) + prev	
			# add in gaussian noise
			#noisy_pos = self.prev_pose + np.random.normal(0,self.res, (2,))
			self.prev_pose = target_pos #(target_pos + noisy_pos)*0.5	

		self.human_pose = PoseStamped()
		self.human_pose.header.frame_id="/frame_id_1"
		self.human_pose.header.stamp = rospy.Time.now()
		# set the current timestamp
		# self.human_pose.header.stamp.secs = curr_time
		self.human_pose.pose.position.x = target_pos[0]
		self.human_pose.pose.position.y = target_pos[1]
		self.human_pose.pose.position.z = 0.0

	def sim_to_real_coord(self, sim_coord):
		"""
		Takes [x,y] coordinate in simulation frame and returns a rotated and 
		shifted	value in the ROS coordinates
		"""
		return [sim_coord[0]*self.res_x + self.real_lower[0], 
						self.real_upper[1] - sim_coord[1]*self.res_y]

	def real_to_sim_coord(self, real_coord):
		"""
		Takes [x,y] coordinate in the ROS real frame, and returns a rotated and 
		shifted	value in the simulation frame
		"""
		return [int(round((real_coord[0] - self.real_lower[0])/self.res_x)),
						int(round((self.real_upper[1] - real_coord[1])/self.res_y))]

if __name__ == '__main__':
	human = LinearHuman()
